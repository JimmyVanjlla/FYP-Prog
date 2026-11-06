import 'package:flutter/material.dart';

import '../../../core/json.dart';

/// Same rule as the server (app/schemas/user.py): digits, spaces, dashes and
/// brackets, an optional leading +, 7 to 30 characters. Checked as the person
/// types, so a typo is caught at the point of entry (Ch4 section 4.4.1).
final _phonePattern = RegExp(r'^\+?[0-9][0-9 ()\-]{5,28}[0-9]$');

String? validateOptionalPhone(String? value) {
  final text = value?.trim() ?? '';
  if (text.isEmpty) return null; // contact details are optional
  return _phonePattern.hasMatch(text) ? null : 'Enter a valid phone number, for example +60 12-345 6789.';
}

/// The four optional contact details a staff account carries.
class ContactControllers {
  final phone = TextEditingController();
  final address = TextEditingController();
  final emergencyName = TextEditingController();
  final emergencyPhone = TextEditingController();

  ContactControllers([Json? from]) {
    if (from != null) load(from);
  }

  void load(Json user) {
    phone.text = (user['phone_number'] as String?) ?? '';
    address.text = (user['address'] as String?) ?? '';
    emergencyName.text = (user['emergency_contact_name'] as String?) ?? '';
    emergencyPhone.text = (user['emergency_contact_phone'] as String?) ?? '';
  }

  /// What the server takes. An emptied field is sent as "", which clears it.
  Map<String, dynamic> toJson() => {
    'phone_number': phone.text.trim(),
    'address': address.text.trim(),
    'emergency_contact_name': emergencyName.text.trim(),
    'emergency_contact_phone': emergencyPhone.text.trim(),
  };

  void dispose() {
    phone.dispose();
    address.dispose();
    emergencyName.dispose();
    emergencyPhone.dispose();
  }
}

class ContactFields extends StatelessWidget {
  final ContactControllers controllers;

  const ContactFields({super.key, required this.controllers});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TextFormField(
          controller: controllers.phone,
          keyboardType: TextInputType.phone,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          decoration: const InputDecoration(labelText: 'Phone number', prefixIcon: Icon(Icons.phone_rounded)),
          validator: validateOptionalPhone,
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: controllers.address,
          keyboardType: TextInputType.streetAddress,
          maxLines: 2,
          maxLength: 300,
          decoration: const InputDecoration(labelText: 'Address', prefixIcon: Icon(Icons.home_rounded)),
        ),
        const SizedBox(height: 4),
        TextFormField(
          controller: controllers.emergencyName,
          maxLength: 150,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(
            labelText: 'Emergency contact name',
            prefixIcon: Icon(Icons.contact_emergency_rounded),
          ),
        ),
        const SizedBox(height: 4),
        TextFormField(
          controller: controllers.emergencyPhone,
          keyboardType: TextInputType.phone,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          decoration: const InputDecoration(
            labelText: 'Emergency contact phone',
            prefixIcon: Icon(Icons.phone_in_talk_rounded),
          ),
          validator: validateOptionalPhone,
        ),
      ],
    );
  }
}

/// Read-only view of the same details, for the staff detail screen.
class ContactSummary extends StatelessWidget {
  final Json user;

  const ContactSummary({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    final emergencyName = user['emergency_contact_name'] as String?;
    final emergencyPhone = user['emergency_contact_phone'] as String?;
    final emergency = [
      if (emergencyName != null && emergencyName.isNotEmpty) emergencyName,
      if (emergencyPhone != null && emergencyPhone.isNotEmpty) emergencyPhone,
    ].join(' · ');
    return Column(
      children: [
        _DetailRow(icon: Icons.email_rounded, label: 'Email', value: user['email'] as String?),
        _DetailRow(icon: Icons.phone_rounded, label: 'Phone', value: user['phone_number'] as String?),
        _DetailRow(icon: Icons.home_rounded, label: 'Address', value: user['address'] as String?),
        _DetailRow(
          icon: Icons.contact_emergency_rounded,
          label: 'Emergency contact',
          value: emergency.isEmpty ? null : emergency,
        ),
      ],
    );
  }
}

class _DetailRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String? value;

  const _DetailRow({required this.icon, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final missing = value == null || value!.trim().isEmpty;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: scheme.primary),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: Theme.of(context).textTheme.labelMedium?.copyWith(color: scheme.onSurfaceVariant)),
                const SizedBox(height: 2),
                Text(
                  missing ? 'Not provided' : value!,
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: missing ? scheme.onSurfaceVariant.withValues(alpha: 0.7) : scheme.onSurface,
                    fontStyle: missing ? FontStyle.italic : FontStyle.normal,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Round initials badge for a person, used on the profile and staff screens.
class PersonAvatar extends StatelessWidget {
  final String name;
  final double radius;

  const PersonAvatar({super.key, required this.name, this.radius = 32});

  String get _initials {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return (parts.first[0] + parts.last[0]).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return CircleAvatar(
      radius: radius,
      backgroundColor: scheme.primaryContainer,
      child: Text(
        _initials,
        style: TextStyle(color: scheme.onPrimaryContainer, fontWeight: FontWeight.w800, fontSize: radius * 0.7),
      ),
    );
  }
}
