import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// FR5.1 / FR5.2 / FR5.5 — what to prep for a service. Each dish's quantity
/// comes pre-filled from the forecast but is always editable ("a starting
/// point, never a lock", Ch4 section 4.4.1). The deviation from the
/// recommendation is shown as it's typed, and once it passes the configured
/// threshold a reason is required right there at the field — not after
/// pressing Confirm.
///
/// A dish with no forecast yet (UC-KO-01 Alt Flow 3a) takes a manual
/// quantity instead of dead-ending.
class PrepScreen extends StatefulWidget {
  const PrepScreen({super.key});

  @override
  State<PrepScreen> createState() => _PrepScreenState();
}

class _PrepData {
  final List<Json> items;
  final Map<int, Json> recommendations;
  final double deviationThreshold;

  _PrepData(this.items, this.recommendations, this.deviationThreshold);
}

class _PrepScreenState extends State<PrepScreen> {
  DateTime _date = DateTime.now();
  String _period = 'Lunch';

  Future<_PrepData> _load() async {
    final api = context.read<AuthState>().api;
    final day = fmtDate(_date);
    final results = await Future.wait([
      api.getJson('/menu-items', query: {'limit': 500}),
      api.getJson('/forecasting/forecasts', query: {
        'date_from': day,
        'date_to': day,
        'meal_period': _period,
        'limit': 500,
      }),
      api.getJson('/kitchen/prep-recommendations', query: {
        'forecast_date': day,
        'meal_period': _period,
        'limit': 500,
      }),
      api.getJson('/config'),
    ]);

    final items = asJsonList(results[0]);
    final forecasted = asJsonList(results[1]).map((f) => f['menu_item_id'] as int).toSet();
    final recs = {for (final r in asJsonList(results[2])) r['menu_item_id'] as int: r};

    // Create (or refresh) the recommendation for every dish that has a
    // forecast but hasn't been confirmed yet, so the numbers shown are the
    // current forecast's, not a stale earlier one.
    final needsGenerating = forecasted.where((id) => recs[id]?['confirmed'] != true).toList();
    await Future.wait(
      needsGenerating.map((id) async {
        recs[id] = asJson(
          await api.postJson('/kitchen/prep-recommendations', {
            'menu_item_id': id,
            'meal_period': _period,
            'forecast_date': day,
          }),
        );
      }),
    );

    items.sort((a, b) {
      final aHas = recs.containsKey(a['menu_item_id']) ? 0 : 1;
      final bHas = recs.containsKey(b['menu_item_id']) ? 0 : 1;
      return aHas != bHas ? aHas.compareTo(bHas) : (a['name'] as String).compareTo(b['name'] as String);
    });
    return _PrepData(items, recs, asDouble(asJson(results[3])['prep_deviation_threshold']));
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          color: Theme.of(context).colorScheme.surfaceContainer,
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.calendar_today_rounded, size: 18),
                  label: Text(friendlyDate(fmtDate(_date))),
                  onPressed: () async {
                    final picked = await showDatePicker(
                      context: context,
                      initialDate: _date,
                      firstDate: DateTime.now().subtract(const Duration(days: 7)),
                      lastDate: DateTime.now().add(const Duration(days: 14)),
                    );
                    if (picked != null) setState(() => _date = picked);
                  },
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: DropdownButtonFormField<String>(
                  isExpanded: true,
                  initialValue: _period,
                  decoration: const InputDecoration(labelText: 'Meal period', contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10)),
                  items: mealPeriods.map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
                  onChanged: (v) => setState(() => _period = v ?? _period),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: AsyncView<_PrepData>(
            key: ValueKey('${fmtDate(_date)}|$_period'),
            load: _load,
            builder: (context, data, reload) => RefreshableList(
              onRefresh: reload,
              empty: const EmptyState(
                icon: Icons.restaurant_menu_outlined,
                message: 'No menu items.',
              ),
              children: [
                for (final item in data.items) ...[
                  _PrepRow(
                    key: ValueKey('${item['menu_item_id']}|${fmtDate(_date)}|$_period'),
                    item: item,
                    recommendation: data.recommendations[item['menu_item_id']],
                    threshold: data.deviationThreshold,
                    date: _date,
                    period: _period,
                    onConfirmed: reload,
                  ),
                  const SizedBox(height: 10),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _PrepRow extends StatefulWidget {
  final Json item;
  final Json? recommendation;
  final double threshold;
  final DateTime date;
  final String period;
  final Future<void> Function() onConfirmed;

  const _PrepRow({
    super.key,
    required this.item,
    required this.recommendation,
    required this.threshold,
    required this.date,
    required this.period,
    required this.onConfirmed,
  });

  @override
  State<_PrepRow> createState() => _PrepRowState();
}

class _PrepRowState extends State<_PrepRow> {
  late final TextEditingController _quantity;
  final _reason = TextEditingController();
  bool _busy = false;

  Json? get _rec => widget.recommendation;
  bool get _confirmed => _rec?['confirmed'] == true;
  bool get _isManual => _rec != null && _rec!['forecast_id'] == null;
  double? get _recommended => _rec == null ? null : asDouble(_rec!['recommended_quantity']);

  @override
  void initState() {
    super.initState();
    final start = _confirmed ? _rec!['confirmed_quantity'] : _rec?['recommended_quantity'];
    _quantity = TextEditingController(text: start == null ? '' : trimNum(start));
    _quantity.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _quantity.dispose();
    _reason.dispose();
    super.dispose();
  }

  double? get _entered => double.tryParse(_quantity.text.trim());

  double? get _deviationPct {
    final rec = _recommended;
    final entered = _entered;
    if (rec == null || entered == null || rec == 0) return null;
    return (entered - rec).abs() / rec * 100;
  }

  bool get _needsReason => (_deviationPct ?? 0) > widget.threshold;

  String? get _quantityError {
    if (_quantity.text.trim().isEmpty) return null;
    final v = _entered;
    if (v == null) return 'Enter a number.';
    if (v < 0) return 'Cannot be negative.';
    return null;
  }

  bool get _canSubmit =>
      !_busy && !_confirmed && _entered != null && _entered! >= 0 && (!_needsReason || _reason.text.trim().isNotEmpty) && (_rec != null || _entered! > 0);

  Future<void> _submit() async {
    setState(() => _busy = true);
    final api = context.read<AuthState>().api;
    final day = fmtDate(widget.date);
    final ok = await runAction(
      context,
      () async {
        // No forecast: record the manual quantity as the recommendation.
        final rec = _rec ??
            asJson(
              await api.postJson('/kitchen/prep-recommendations', {
                'menu_item_id': widget.item['menu_item_id'],
                'meal_period': widget.period,
                'forecast_date': day,
                'manual_quantity': _quantity.text.trim(),
              }),
            );
        await api.confirmPrep(
          recommendationId: rec['recommendation_id'] as int,
          confirmedQuantity: _quantity.text.trim(),
          deviationReason: _needsReason ? _reason.text.trim() : null,
        );
      },
      success: '${widget.item['name']} confirmed.',
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) await widget.onConfirmed();
  }

  @override
  Widget build(BuildContext context) {
    final rec = _recommended;
    final dev = _deviationPct;
    final scheme = Theme.of(context).colorScheme;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    widget.item['name'] as String,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ),
                if (_confirmed)
                  const SeverityChip(label: 'Confirmed', color: Severity.ok)
                else if (_rec == null)
                  const SeverityChip(label: 'No forecast', color: Severity.warning)
                else if (_isManual)
                  const SeverityChip(label: 'Manual', color: Severity.warning),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              rec == null
                  ? 'No forecast for this service yet. Enter what you plan to prep.'
                  : 'Recommended: ${trimNum(rec)} portions',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _quantity,
              enabled: !_confirmed && !_busy,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                labelText: 'Quantity to prep',
                suffixText: 'portions',
                errorText: _quantityError,
                helperText: dev == null || _confirmed
                    ? null
                    : dev == 0
                        ? 'Matches the recommendation'
                        : '${dev.toStringAsFixed(0)}% ${(_entered ?? 0) > (rec ?? 0) ? 'above' : 'below'} the recommendation',
              ),
            ),
            if (_needsReason && !_confirmed) ...[
              const SizedBox(height: 10),
              TextField(
                controller: _reason,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(
                  labelText: 'Reason for the change (required)',
                  helperText: 'Changes over ${trimNum(widget.threshold)}% need a reason.',
                  errorText: _reason.text.trim().isEmpty ? 'Please explain the change.' : null,
                ),
              ),
            ],
            if (_confirmed && (_rec?['deviation_reason'] as String?)?.isNotEmpty == true) ...[
              const SizedBox(height: 8),
              Text('Reason: ${_rec!['deviation_reason']}', style: Theme.of(context).textTheme.bodySmall),
            ],
            if (!_confirmed) ...[
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _canSubmit ? _submit : null,
                child: _busy
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Confirm'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
