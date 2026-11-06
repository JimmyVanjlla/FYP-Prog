import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';
import 'contact_fields.dart';

/// Module 1 — "profile and credential management". Everyone can see and edit
/// their own name and contact details and change their password. Their role
/// and email are shown but not editable: a role is a permission only a
/// Restaurant Manager or Owner grants, and the email is the login.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  int _version = 0;

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('My profile')),
      body: AsyncView<Json>(
        key: ValueKey(_version),
        load: () async => asJson(await api.getJson('/users/me')),
        builder: (context, user, reload) => _ProfileBody(
          user: user,
          onSaved: () async => setState(() => _version++),
        ),
      ),
    );
  }
}

class _ProfileBody extends StatefulWidget {
  final Json user;
  final Future<void> Function() onSaved;

  const _ProfileBody({required this.user, required this.onSaved});

  @override
  State<_ProfileBody> createState() => _ProfileBodyState();
}

class _ProfileBodyState extends State<_ProfileBody> {
  final _detailsKey = GlobalKey<FormState>();
  final _passwordKey = GlobalKey<FormState>();
  late final _name = TextEditingController(text: widget.user['name'] as String);
  late final _contact = ContactControllers(widget.user);
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();
  bool _savingDetails = false;
  bool _savingPassword = false;

  @override
  void dispose() {
    _name.dispose();
    _contact.dispose();
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _saveDetails() async {
    if (!_detailsKey.currentState!.validate()) return;
    final api = context.read<AuthState>().api;
    setState(() => _savingDetails = true);
    final ok = await runAction(
      context,
      () => api.patchJson('/users/me', {'name': _name.text.trim(), ..._contact.toJson()}),
      success: 'Profile saved.',
    );
    if (mounted) setState(() => _savingDetails = false);
    if (ok && mounted) {
      await context.read<AuthState>().loadProfile(); // the menu header shows the name
      await widget.onSaved();
    }
  }

  Future<void> _changePassword() async {
    if (!_passwordKey.currentState!.validate()) return;
    final api = context.read<AuthState>().api;
    setState(() => _savingPassword = true);
    final ok = await runAction(
      context,
      () => api.postJson('/users/me/password', {
        'current_password': _current.text,
        'new_password': _next.text,
      }),
      success: 'Password changed.',
    );
    if (!mounted) return;
    setState(() => _savingPassword = false);
    if (ok) {
      _current.clear();
      _next.clear();
      _confirm.clear();
      _passwordKey.currentState?.reset();
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final user = widget.user;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              children: [
                PersonAvatar(name: user['name'] as String, radius: 34),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(user['name'] as String, style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 4),
                      Text(user['email'] as String, style: TextStyle(color: scheme.onSurfaceVariant)),
                      const SizedBox(height: 8),
                      Chip(
                        avatar: Icon(Icons.badge_rounded, size: 16, color: scheme.primary),
                        label: Text(user['role'] as String),
                        visualDensity: VisualDensity.compact,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Text(
            'Your role and email can only be changed by a Restaurant Manager or Owner.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ),
        const SizedBox(height: 20),
        const SectionHeader(icon: Icons.person_rounded, label: 'Personal details'),
        Form(
          key: _detailsKey,
          child: Column(
            children: [
              TextFormField(
                controller: _name,
                textCapitalization: TextCapitalization.words,
                maxLength: 150,
                decoration: const InputDecoration(labelText: 'Full name', prefixIcon: Icon(Icons.person_outline_rounded)),
                validator: (v) => (v == null || v.trim().isEmpty) ? 'Your name cannot be empty.' : null,
              ),
              const SizedBox(height: 4),
              ContactFields(controllers: _contact),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _savingDetails ? null : _saveDetails,
                  icon: _savingDetails
                      ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.save_rounded),
                  label: const Text('Save changes'),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 28),
        const SectionHeader(icon: Icons.lock_rounded, label: 'Change password'),
        Form(
          key: _passwordKey,
          child: Column(
            children: [
              TextFormField(
                controller: _current,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Current password'),
                validator: (v) => (v == null || v.isEmpty) ? 'Enter your current password.' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _next,
                obscureText: true,
                autovalidateMode: AutovalidateMode.onUserInteraction,
                decoration: const InputDecoration(labelText: 'New password', helperText: 'At least 8 characters.'),
                validator: (v) => (v == null || v.length < 8) ? 'At least 8 characters.' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _confirm,
                obscureText: true,
                autovalidateMode: AutovalidateMode.onUserInteraction,
                decoration: const InputDecoration(labelText: 'Repeat the new password'),
                validator: (v) => v != _next.text ? 'The two passwords do not match.' : null,
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: _savingPassword ? null : _changePassword,
                  icon: const Icon(Icons.key_rounded),
                  label: const Text('Change password'),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
      ],
    );
  }
}
