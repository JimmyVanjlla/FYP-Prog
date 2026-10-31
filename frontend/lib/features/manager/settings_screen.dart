import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// FR3.3 / FR7.5 and the other restaurant-wide thresholds every module
/// reads from SystemConfig. Each field validates inline, with the same
/// ranges the API enforces (FR7.5: leftover rate must be 0-100%).
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<Json>(
      load: () async => asJson(await api.getJson('/config')),
      builder: (context, config, reload) => _SettingsForm(config: config, onSaved: reload),
    );
  }
}

class _Field {
  final String key;
  final String label;
  final String helper;
  final String suffix;
  final double min;
  final double? max;
  final bool integer;
  final bool minExclusive;

  const _Field(
    this.key,
    this.label,
    this.helper, {
    this.suffix = '',
    this.min = 0,
    this.max,
    this.integer = false,
    this.minExclusive = false,
  });

  String? validate(String? raw) {
    final text = raw?.trim() ?? '';
    final value = double.tryParse(text);
    if (value == null) return 'Enter a number.';
    if (integer && value != value.roundToDouble()) return 'Whole numbers only.';
    if (minExclusive ? value <= min : value < min) {
      return minExclusive ? 'Must be greater than ${trimNum(min)}.' : 'Cannot be below ${trimNum(min)}.';
    }
    if (max != null && value > max!) return 'Cannot be above ${trimNum(max)}.';
    return null;
  }
}

const _fields = [
  _Field(
    'default_low_stock_threshold',
    'Default low-stock threshold',
    'Used for any ingredient without its own threshold.',
  ),
  _Field(
    'leftover_rate_threshold',
    'Leftover rate threshold',
    'Dishes above this get a portion-size review.',
    suffix: '%',
    max: 100,
  ),
  _Field(
    'prep_deviation_threshold',
    'Prep deviation threshold',
    'Changing a prep quantity by more than this needs a reason.',
    suffix: '%',
    max: 100,
  ),
  _Field(
    'portions_per_staff_ratio',
    'Portions per staff member',
    'Drives the staffing recommendations.',
    min: 0,
    minExclusive: true,
  ),
  _Field(
    'monthly_budget_limit',
    'Default monthly budget',
    'Fallback when no budget is set for a month.',
    suffix: 'RM',
    min: 0,
    minExclusive: true,
  ),
  _Field(
    'delivery_deviation_threshold',
    'Delivery deviation threshold',
    'A received quantity off by more than this is reported as a discrepancy.',
    suffix: '%',
    max: 100,
  ),
  _Field(
    'near_expiry_window_days',
    'Near-expiry window',
    'Batches expiring within this many days are flagged.',
    suffix: 'days',
    integer: true,
  ),
];

class _SettingsForm extends StatefulWidget {
  final Json config;
  final Future<void> Function() onSaved;

  const _SettingsForm({required this.config, required this.onSaved});

  @override
  State<_SettingsForm> createState() => _SettingsFormState();
}

class _SettingsFormState extends State<_SettingsForm> {
  final _formKey = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _controllers;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _controllers = {
      for (final f in _fields) f.key: TextEditingController(text: trimNum(widget.config[f.key])),
    };
  }

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final api = context.read<AuthState>().api;
    final body = {
      for (final f in _fields)
        f.key: f.integer ? int.parse(_controllers[f.key]!.text.trim()) : _controllers[f.key]!.text.trim(),
    };
    final ok = await runAction(context, () => api.patchJson('/config', body), success: 'Settings saved.');
    if (mounted) setState(() => _saving = false);
    if (ok) await widget.onSaved();
  }

  @override
  Widget build(BuildContext context) {
    final through = widget.config['stock_consumption_applied_through'];
    return Form(
      key: _formKey,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const SectionHeader(icon: Icons.tune_rounded, label: 'Restaurant-wide settings'),
          const SizedBox(height: 8),
          for (final f in _fields) ...[
            TextFormField(
              controller: _controllers[f.key],
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                labelText: f.label,
                helperText: f.helper,
                helperMaxLines: 2,
                suffixText: f.suffix.isEmpty ? null : f.suffix,
              ),
              validator: f.validate,
            ),
            const SizedBox(height: 16),
          ],
          if (through != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Text(
                'Stock has been reconciled for consumption through ${friendlyDate(through)}.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Save settings'),
          ),
        ],
      ),
    );
  }
}
