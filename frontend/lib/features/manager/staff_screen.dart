import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/dialogs.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';
import 'staff_detail_screen.dart';

/// FR1.4 / FR1.5 — a Restaurant Manager creates, deactivates and
/// reassigns staff accounts, keeps their contact details, and reviews the
/// audit trail of what each account has done. Beyond the very first
/// Manager/Owner, this screen is the only way an account gets created.
class StaffScreen extends StatefulWidget {
  const StaffScreen({super.key});

  @override
  State<StaffScreen> createState() => _StaffScreenState();
}

class _StaffScreenState extends State<StaffScreen> {
  int _version = 0;

  /// Something changed on one tab (an account was deleted, restored, added):
  /// reload them all.
  void _changed() => setState(() => _version++);

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Column(
        children: [
          const TabBar(
            tabs: [
              Tab(icon: Icon(Icons.groups_rounded), text: 'Accounts'),
              Tab(icon: Icon(Icons.delete_sweep_rounded), text: 'Deleted'),
              Tab(icon: Icon(Icons.history_rounded), text: 'Activity log'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                _AccountsTab(version: _version, onChanged: _changed),
                _DeletedTab(version: _version, onChanged: _changed),
                _ActivityTab(version: _version),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AccountsTab extends StatelessWidget {
  final int version;
  final VoidCallback onChanged;

  const _AccountsTab({required this.version, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<List<Json>>(
      key: ValueKey('accounts-$version'),
      load: () async => asJsonList(await api.getJson('/users', query: {'limit': 500})),
      builder: (context, users, reload) => RefreshableList(
        onRefresh: reload,
        children: [
          // Deactivated accounts first, so they are not forgotten at the
          // bottom of a long list; then by name within each group.
          for (final u in _deactivatedFirst(users)) ...[
            _UserTile(user: u, onChanged: () async => onChanged()),
            const SizedBox(height: 10),
          ],
          AddRow(
            label: 'Add staff account',
            onTap: () async {
              final created = await Navigator.of(context).push<bool>(
                MaterialPageRoute(builder: (_) => const StaffFormScreen()),
              );
              if (created == true) onChanged();
            },
          ),
        ],
      ),
    );
  }
}

/// Accounts deleted in the last 60 days. They are out of the staff list, can be
/// restored here, and are removed for good once the 60 days are up.
class _DeletedTab extends StatelessWidget {
  final int version;
  final VoidCallback onChanged;

  const _DeletedTab({required this.version, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    final actor = context.read<AuthState>().role;
    return AsyncView<List<Json>>(
      key: ValueKey('deleted-$version'),
      load: () async => asJsonList(await api.getJson('/users', query: {'deleted': true, 'limit': 500})),
      builder: (context, users, reload) => RefreshableList(
        onRefresh: reload,
        empty: const EmptyState(
          icon: Icons.delete_sweep_outlined,
          message: 'No deleted accounts.',
          detail: 'A deactivated account you delete is kept here for 60 days, then removed for good.',
        ),
        children: [
          for (final u in users)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const IconBadge(icon: Icons.person_off_rounded, color: Severity.critical),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(u['name'] as String, style: const TextStyle(fontWeight: FontWeight.w700)),
                                Text('${u['role']}\n${u['email']}', style: Theme.of(context).textTheme.bodySmall),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _removalNote(u['deleted_at']),
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
                      ),
                      if (Roles.canManage(actor, u['role'] as String)) ...[
                        const SizedBox(height: 10),
                        OutlinedButton.icon(
                          icon: const Icon(Icons.restore_rounded),
                          label: const Text('Restore account'),
                          onPressed: () async {
                            final ok = await runAction(
                              context,
                              () => api.postJson('/users/${u['user_id']}/restore'),
                              success: '${u['name']} restored. The account is deactivated until you reactivate it.',
                            );
                            if (ok) onChanged();
                          },
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// "Deleted 12 Nov · 47 days left to restore".
String _removalNote(dynamic deletedAt, {DateTime? now}) {
  final when = parseDate(deletedAt);
  if (when == null) return '';
  final daysLeft = deletionRetentionDays - (now ?? DateTime.now()).difference(when).inDays;
  final left = daysLeft <= 0 ? 'removed permanently today' : '$daysLeft ${daysLeft == 1 ? 'day' : 'days'} left to restore';
  return 'Deleted ${shortDate(deletedAt)}  ·  $left';
}

/// How long a deleted account can be restored before it is removed for good.
const deletionRetentionDays = 60;

/// Deactivated accounts first, then by name (case-insensitive).
List<Json> _deactivatedFirst(List<Json> users) {
  final sorted = [...users];
  sorted.sort((a, b) {
    final aActive = a['is_active'] as bool;
    final bActive = b['is_active'] as bool;
    if (aActive != bActive) return aActive ? 1 : -1;
    return (a['name'] as String).toLowerCase().compareTo((b['name'] as String).toLowerCase());
  });
  return sorted;
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
        onTap: () async {
          await Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => StaffDetailScreen(user: user)),
          );
          await onChanged(); // details may have been edited
        },
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
            if (Roles.canManage(context.read<AuthState>().role, user['role'] as String))
              PopupMenuButton<String>(
              tooltip: 'Manage account',
              onSelected: (choice) => _onSelected(context, choice),
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'role', child: Text('Change role')),
                PopupMenuItem(value: 'toggle', child: Text(active ? 'Deactivate' : 'Reactivate')),
                if (!active) const PopupMenuItem(value: 'delete', child: Text('Delete account')),
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
    if (choice == 'delete') {
      final sure = await confirmAction(
        context,
        title: 'Delete ${user['name']}?',
        message: 'The account leaves the staff list and goes to the Deleted tab. You can restore it there for '
            '$deletionRetentionDays days; after that it is removed permanently.',
        confirmLabel: 'Delete',
      );
      if (!sure || !context.mounted) return;
      final ok = await runAction(context, () => api.deleteJson('/users/$id'), success: 'Account deleted.');
      if (ok) await onChanged();
      return;
    }
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
            items: Roles.assignableBy(context.read<AuthState>().role)
                .map((r) => DropdownMenuItem(value: r, child: Text(r)))
                .toList(),
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
  final int version;

  const _ActivityTab({required this.version});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<({List<Json> logs, Map<int, String> names})>(
      key: ValueKey('activity-$version'),
      load: () async {
        final logs = asJsonList(await api.getJson('/users/audit-logs', query: {'limit': 200}));
        final users = asJsonList(await api.getJson('/users', query: {'limit': 500}));
        final deleted = asJsonList(await api.getJson('/users', query: {'deleted': true, 'limit': 500}));
        return (
          logs: logs,
          names: {for (final u in [...users, ...deleted]) u['user_id'] as int: u['name'] as String},
        );
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
