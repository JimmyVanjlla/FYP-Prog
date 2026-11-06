import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';
import '../shared/profile/contact_fields.dart';

/// A new account: the sign-in details and role, then the optional contact
/// details. Only a Restaurant Manager or Owner reaches this screen. Pops with
/// `true` once the account exists.
class StaffFormScreen extends StatefulWidget {
  const StaffFormScreen({super.key});

  @override
  State<StaffFormScreen> createState() => _StaffFormScreenState();
}

class _StaffFormScreenState extends State<StaffFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _contact = ContactControllers();
  String _role = Roles.kitchenStaff;
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    _contact.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    if (!_formKey.currentState!.validate()) return;
    final api = context.read<AuthState>().api;
    setState(() => _saving = true);
    final ok = await runAction(
      context,
      () => api.postJson('/users', {
        'name': _name.text.trim(),
        'email': _email.text.trim(),
        'password': _password.text,
        'role': _role,
        ..._contact.toJson(),
      }),
      success: 'Account created.',
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New staff account')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const SectionHeader(icon: Icons.login_rounded, label: 'Sign-in'),
            TextFormField(
              controller: _name,
              textCapitalization: TextCapitalization.words,
              maxLength: 150,
              decoration: const InputDecoration(labelText: 'Full name', prefixIcon: Icon(Icons.person_outline_rounded)),
              validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
            ),
            const SizedBox(height: 4),
            TextFormField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autovalidateMode: AutovalidateMode.onUserInteraction,
              decoration: const InputDecoration(labelText: 'Email', prefixIcon: Icon(Icons.email_outlined)),
              validator: (v) {
                final text = v?.trim() ?? '';
                return RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(text) ? null : 'Enter a valid email.';
              },
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _password,
              obscureText: true,
              autovalidateMode: AutovalidateMode.onUserInteraction,
              decoration: const InputDecoration(
                labelText: 'Temporary password',
                helperText: 'They can change it from their profile.',
                prefixIcon: Icon(Icons.lock_outline_rounded),
              ),
              validator: (v) => (v == null || v.length < 8) ? 'At least 8 characters.' : null,
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _role,
              decoration: const InputDecoration(labelText: 'Role', prefixIcon: Icon(Icons.badge_outlined)),
              items: Roles.all.map((r) => DropdownMenuItem(value: r, child: Text(r))).toList(),
              onChanged: (v) => setState(() => _role = v ?? _role),
            ),
            const SizedBox(height: 24),
            const SectionHeader(icon: Icons.contacts_rounded, label: 'Contact details (optional)'),
            ContactFields(controllers: _contact),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _saving ? null : _create,
              icon: _saving
                  ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.person_add_alt_1_rounded),
              label: const Text('Create account'),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}

/// One staff member's details, with a way for a Manager or Owner to correct
/// them (name and contact details; the role and active status are changed
/// from the list, as before).
class StaffDetailScreen extends StatefulWidget {
  final Json user;

  const StaffDetailScreen({super.key, required this.user});

  @override
  State<StaffDetailScreen> createState() => _StaffDetailScreenState();
}

class _StaffDetailScreenState extends State<StaffDetailScreen> {
  late Json _user = widget.user;
  bool _editing = false;
  bool _saving = false;
  final _formKey = GlobalKey<FormState>();
  late final _name = TextEditingController(text: _user['name'] as String);
  late final _contact = ContactControllers(_user);

  @override
  void dispose() {
    _name.dispose();
    _contact.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    final api = context.read<AuthState>().api;
    final id = _user['user_id'] as int;
    setState(() => _saving = true);
    Json? updated;
    final ok = await runAction(
      context,
      () async => updated = asJson(await api.patchJson('/users/$id', {'name': _name.text.trim(), ..._contact.toJson()})),
      success: 'Details saved.',
    );
    if (!mounted) return;
    setState(() {
      _saving = false;
      if (ok && updated != null) {
        _user = updated!;
        _editing = false;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final active = _user['is_active'] as bool;
    return Scaffold(
      appBar: AppBar(
        title: Text(_editing ? 'Edit details' : 'Staff details'),
        leading: BackButton(onPressed: () => Navigator.pop(context, true)),
        actions: [
          if (!_editing)
            IconButton(tooltip: 'Edit details', icon: const Icon(Icons.edit_rounded), onPressed: () => setState(() => _editing = true)),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  PersonAvatar(name: _user['name'] as String, radius: 34),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(_user['name'] as String, style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 4),
                        Text(_user['role'] as String, style: TextStyle(color: scheme.onSurfaceVariant)),
                        const SizedBox(height: 8),
                        SeverityChip(label: active ? 'Active' : 'Deactivated', color: active ? Severity.ok : Severity.critical),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          if (!_editing) ...[
            const SectionHeader(icon: Icons.contacts_rounded, label: 'Contact details'),
            Card(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: ContactSummary(user: _user),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Account created ${friendlyDate(_user['created_at'])}.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ] else
            Form(
              key: _formKey,
              child: Column(
                children: [
                  TextFormField(
                    controller: _name,
                    textCapitalization: TextCapitalization.words,
                    maxLength: 150,
                    decoration: const InputDecoration(labelText: 'Full name', prefixIcon: Icon(Icons.person_outline_rounded)),
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Required.' : null,
                  ),
                  const SizedBox(height: 4),
                  ContactFields(controllers: _contact),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _saving ? null : () => setState(() => _editing = false),
                          child: const Text('Cancel'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton(onPressed: _saving ? null : _save, child: const Text('Save')),
                      ),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
