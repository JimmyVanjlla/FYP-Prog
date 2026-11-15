import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/clock.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// The standard answers to "how much was left over?": a share of what the
/// kitchen prepared for that dish and meal period.
const leftoverLevels = [0, 25, 50, 75, 100];

/// The quantity a leftover percentage is taken of: what was confirmed in Prep,
/// else what was recommended; null if nothing was recorded for the dish.
double? leftoverPrepBasis(Json? recommendation) {
  if (recommendation == null) return null;
  final quantity = recommendation['confirmed'] == true
      ? recommendation['confirmed_quantity']
      : recommendation['recommended_quantity'];
  final q = asDouble(quantity);
  return q > 0 ? q : null;
}

/// Module 5 — FR5.3. Kitchen Staff log how much of a dish was left at the end
/// of a meal period: none, a quarter, half, three quarters or all of what was
/// prepared. There are no quantities to type: the amount is a share of the
/// quantity confirmed in Prep, so every log means the same thing whoever makes
/// it.
class LeftoverLogScreen extends StatefulWidget {
  const LeftoverLogScreen({super.key});

  @override
  State<LeftoverLogScreen> createState() => _LeftoverLogScreenState();
}

class _LeftoverLogScreenState extends State<LeftoverLogScreen> {
  DateTime _date = restaurantToday();
  String _period = 'Lunch';
  int? _dishId;
  int? _percent;
  bool _saving = false;

  Future<({List<Json> dishes, Map<int, Json> prep})> _load() async {
    final api = context.read<AuthState>().api;
    final results = await Future.wait([
      api.getJson('/menu-items', query: {'limit': 500}),
      api.getJson('/kitchen/prep-recommendations', query: {
        'forecast_date': fmtDate(_date),
        'meal_period': _period,
        'limit': 500,
      }),
    ]);
    return (
      dishes: asJsonList(results[0]),
      prep: {for (final r in asJsonList(results[1])) r['menu_item_id'] as int: r},
    );
  }

  Future<void> _save(int dishId) async {
    setState(() => _saving = true);
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/kitchen/leftover-logs', {
        'menu_item_id': dishId,
        'service_period_date': fmtDate(_date),
        'meal_period': _period,
        'leftover_percent': _percent,
      }),
      success: 'Leftover log saved.',
    );
    if (!mounted) return;
    setState(() {
      _saving = false;
      if (ok) _percent = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AsyncView<({List<Json> dishes, Map<int, Json> prep})>(
      key: ValueKey('${fmtDate(_date)}|$_period'),
      load: _load,
      builder: (context, data, reload) {
        final served = data.dishes
            .where((d) => ((d['meal_periods'] as List<dynamic>?) ?? const ['Lunch', 'Dinner']).contains(_period))
            .toList();
        final dishId = served.any((d) => d['menu_item_id'] == _dishId) ? _dishId : (served.isEmpty ? null : served.first['menu_item_id'] as int);
        final basis = dishId == null ? null : leftoverPrepBasis(data.prep[dishId]);

        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Row(
              children: [
                const IconBadge(icon: Icons.restaurant_rounded),
                const SizedBox(width: 12),
                Expanded(child: Text('Log end-of-service leftovers', style: Theme.of(context).textTheme.titleLarge)),
              ],
            ),
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.calendar_today_rounded, size: 18),
                    label: Text(friendlyDate(fmtDate(_date))),
                    onPressed: () async {
                      final picked = await showDatePicker(
                        context: context,
                        initialDate: _date,
                        firstDate: restaurantToday().subtract(const Duration(days: 7)),
                        lastDate: restaurantToday(),
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
                    decoration: const InputDecoration(
                      labelText: 'Meal period',
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    ),
                    items: mealPeriods.map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
                    onChanged: (v) => setState(() => _period = v ?? _period),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (served.isEmpty)
              EmptyState(
                icon: Icons.restaurant_menu_outlined,
                message: 'No dishes are served at $_period.',
              )
            else ...[
              DropdownButtonFormField<int>(
                isExpanded: true,
                initialValue: dishId,
                decoration: const InputDecoration(labelText: 'Dish'),
                items: [
                  for (final d in served) DropdownMenuItem(value: d['menu_item_id'] as int, child: Text(d['name'] as String)),
                ],
                onChanged: (v) => setState(() {
                  _dishId = v;
                  _percent = null;
                }),
              ),
              const SizedBox(height: 16),
              _BasisCard(basis: basis, period: _period, date: _date),
              const SizedBox(height: 20),
              Text('How much was left over?', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  for (final level in leftoverLevels)
                    ChoiceChip(
                      label: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                        child: Text(level == 0 ? 'None' : '$level%', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                      ),
                      selected: _percent == level,
                      onSelected: basis == null ? null : (_) => setState(() => _percent = level),
                    ),
                ],
              ),
              if (basis != null && _percent != null) ...[
                const SizedBox(height: 10),
                Text(
                  'About ${(basis * _percent! / 100).round()} of ${basis.round()} portions',
                  style: TextStyle(color: scheme.onSurfaceVariant),
                ),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: (_saving || dishId == null || basis == null || _percent == null) ? null : () => _save(dishId),
                child: _saving
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Save log'),
              ),
            ],
          ],
        );
      },
    );
  }
}

/// What the percentage will be taken of, or why there is nothing to take it of.
class _BasisCard extends StatelessWidget {
  final double? basis;
  final String period;
  final DateTime date;

  const _BasisCard({required this.basis, required this.period, required this.date});

  @override
  Widget build(BuildContext context) {
    final ok = basis != null;
    final color = ok ? Severity.ok : Severity.warning;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Row(
        children: [
          Icon(ok ? Icons.check_circle_rounded : Icons.error_rounded, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              ok
                  ? 'Based on the ${basis!.round()} portions prepared for $period.'
                  : 'No prep was recorded for this dish at $period on ${friendlyDate(fmtDate(date))}. '
                      'Confirm it in Prep first, so there is something to take a percentage of.',
            ),
          ),
        ],
      ),
    );
  }
}
