import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// FR1.4 / FR1.5 — the Restaurant Manager creates, deactivates and
/// reassigns staff accounts, and reviews the audit trail of what each
/// account has done. Beyond the first Manager/Owner (who can self-register),
/// this screen is the only way a Manager/Owner account gets created.
class StaffScreen extends StatelessWidget {
  const StaffScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const DefaultTabController(
      length: 2,
      child: Column(
        children: [
          TabBar(
            tabs: [
              Tab(icon: Icon(Icons.groups_rounded), text: 'Accounts'),
              Tab(icon: Icon(Icons.history_rounded), text: 'Activity log'),
            ],
          ),
          Expanded(child: TabBarView(children: [_AccountsTab(), _ActivityTab()])),
        ],
      ),
    );
  }
}

class _AccountsTab extends StatelessWidget {
  const _AccountsTab();

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<List<Json>>(
      load: () async => asJsonList(await api.getJson('/users', query: {'limit': 500})),
      builder: (context, users, reload) => RefreshableList(
        onRefresh: reload,
        children: [
          for (final u in users) ...[
            _UserTile(user: u, onChanged: reload),
            const SizedBox(height: 10),
          ],
          AddRow(label: 'Add staff account', onTap: () => _showCreateDialog(context, reload)),
        ],
      ),
    );
  }

  Future<void> _showCreateDialog(BuildContext context, Future<void> Function() reload) async {
    final name = TextEditingController();
    final email = TextEditingController();
    final password = TextEditingController();
    String role = Roles.kitchenStaff;
    final formKey = GlobalKey<FormState>();

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('New staff account'),
          content: SingleChildScrollView(
            child: Form(
              key: formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: name,
                    decoration: const InputDecoration(labelText: 'Full name'),
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'Email'),
                    validator: (v) => (v == null || !v.contains('@')) ? 'Enter a valid email.' : null,
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: password,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: 'Temporary password'),
                    validator: (v) => (v == null || v.length < 8) ? 'At least 8 characters.' : null,
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: role,
                    decoration: const InputDecoration(labelText: 'Role'),
                    items: Roles.all.map((r) => DropdownMenuItem(value: r, child: Text(r))).toList(),
                    onChanged: (v) => setState(() => role = v ?? role),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (formKey.currentState!.validate()) Navigator.pop(context, true);
              },
              child: const Text('Create'),
            ),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/users', {
        'name': name.text.trim(),
        'email': email.text.trim(),
        'password': password.text,
        'role': role,
      }),
      success: 'Account created.',
    );
    if (ok) await reload();
  }
}

class _UserTile extends StatelessWidget {
  final Json user;
  final Future<void> Function() onChanged;

  const _UserTile({required this.user, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final active = user['is_active'] as bool;
    return Card(
      child: ListTile(
        leading: IconBadge(
          icon: active ? Icons.person_rounded : Icons.person_off_rounded,
          color: active ? null : Severity.critical,
        ),
        title: Text(user['name'] as String),
        subtitle: Text('${user['role']}\n${user['email']}'),
        isThreeLine: true,
        trailing: Wrap(
          spacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SeverityChip(
              label: active ? 'Active' : 'Deactivated',
              color: active ? Severity.ok : Severity.critical,
            ),
            PopupMenuButton<String>(
              tooltip: 'Manage account',
              onSelected: (choice) => _onSelected(context, choice),
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'role', child: Text('Change role')),
                PopupMenuItem(value: 'toggle', child: Text(active ? 'Deactivate' : 'Reactivate')),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _onSelected(BuildContext context, String choice) async {
    final api = context.read<AuthState>().api;
    final id = user['user_id'] as int;
    if (choice == 'toggle') {
      final active = user['is_active'] as bool;
      final ok = await runAction(
        context,
        () => api.patchJson('/users/$id', {'is_active': !active}),
        success: active ? 'Account deactivated.' : 'Account reactivated.',
      );
      if (ok) await onChanged();
      return;
    }
    String role = user['role'] as String;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: Text('Change role for ${user['name']}'),
          content: DropdownButtonFormField<String>(
            initialValue: role,
            decoration: const InputDecoration(labelText: 'Role'),
            items: Roles.all.map((r) => DropdownMenuItem(value: r, child: Text(r))).toList(),
            onChanged: (v) => setState(() => role = v ?? role),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Save')),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final ok = await runAction(
      context,
      () => api.patchJson('/users/$id', {'role': role}),
      success: 'Role updated.',
    );
    if (ok) await onChanged();
  }
}

class _ActivityTab extends StatelessWidget {
  const _ActivityTab();

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<({List<Json> logs, Map<int, String> names})>(
      load: () async {
        final logs = asJsonList(await api.getJson('/users/audit-logs', query: {'limit': 200}));
        final users = asJsonList(await api.getJson('/users', query: {'limit': 500}));
        return (logs: logs, names: {for (final u in users) u['user_id'] as int: u['name'] as String});
      },
      builder: (context, data, reload) => RefreshableList(
        onRefresh: reload,
        empty: const EmptyState(icon: Icons.history_rounded, message: 'No activity recorded yet.'),
        children: [
          for (final entry in data.logs)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Card(
                child: ListTile(
                  dense: true,
                  leading: const Icon(Icons.bolt_rounded),
                  title: Text(entry['action'] as String),
                  subtitle: Text(
                    '${data.names[entry['user_id']] ?? 'User #${entry['user_id']}'}  ·  ${friendlyDateTime(entry['timestamp'])}',
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
