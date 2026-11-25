import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/clock.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// Module 5 — FR5.3, now worked out rather than typed in. For each dish at a
/// meal period the screen shows what Kitchen Staff confirmed in Prep, the
/// portions actually served (completed orders) and the leftover:
///
///     leftover = confirmed prep - portions served
///
/// Recording saves those figures, which feed the waste cost, the portion
/// reviews and the forecast. Nobody reports a quantity by hand.
class LeftoverLogScreen extends StatefulWidget {
  const LeftoverLogScreen({super.key});

  @override
  State<LeftoverLogScreen> createState() => _LeftoverLogScreenState();
}

class _LeftoverLogScreenState extends State<LeftoverLogScreen> {
  DateTime _date = restaurantToday();
  String _period = 'Lunch';
  int _version = 0;
  bool _saving = false;

  Future<Json> _load() async {
    final api = context.read<AuthState>().api;
    return asJson(
      await api.getJson('/kitchen/leftover-summary', query: {
        'service_date': fmtDate(_date),
        'meal_period': _period,
      }),
    );
  }

  Future<void> _record() async {
    setState(() => _saving = true);
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/kitchen/leftovers/record', {
        'service_date': fmtDate(_date),
        'meal_period': _period,
      }),
      success: 'Leftovers recorded.',
    );
    if (!mounted) return;
    setState(() {
      _saving = false;
      if (ok) _version++;
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AsyncView<Json>(
      key: ValueKey('${fmtDate(_date)}|$_period|$_version'),
      load: _load,
      builder: (context, summary, reload) {
        final dishes = asJsonList(summary['dishes']);
        final open = (summary['open_orders'] as num?)?.toInt() ?? 0;
        final measured = dishes.where((d) => d['prep_confirmed'] == true).toList();
        final prepared = measured.fold<double>(0, (a, d) => a + asDouble(d['prepared']));
        final left = measured.fold<double>(0, (a, d) => a + asDouble(d['leftover']));
        final allRecorded = measured.isNotEmpty && measured.every((d) => d['recorded'] == true);

        return RefreshableList(
          onRefresh: reload,
          children: [
            Row(
              children: [
                const IconBadge(icon: Icons.restaurant_rounded),
                const SizedBox(width: 12),
                Expanded(child: Text('Leftovers', style: Theme.of(context).textTheme.titleLarge)),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'Worked out for you: what was prepared minus what was served.',
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 16),
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
            if (open > 0)
              _Note(
                icon: Icons.hourglass_bottom_rounded,
                color: Severity.warning,
                text: '$open ${open == 1 ? 'order is' : 'orders are'} not completed yet, so '
                    '${open == 1 ? 'it is' : 'they are'} not counted as served. Finish them in Orders first.',
              ),
            if (dishes.isEmpty)
              EmptyState(
                icon: Icons.restaurant_menu_outlined,
                message: 'No dishes are served at $_period.',
              )
            else ...[
              for (final d in dishes) _DishRow(dish: d),
              const SizedBox(height: 12),
              if (measured.isNotEmpty)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Row(
                      children: [
                        const Icon(Icons.pie_chart_outline_rounded),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            'Overall ${left.round()} of ${prepared.round()} portions left over '
                            '(${prepared == 0 ? 0 : (left / prepared * 100).round()}%).',
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 14),
              FilledButton(
                onPressed: (_saving || measured.isEmpty) ? null : _record,
                child: _saving
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : Text(allRecorded ? 'Update recorded leftovers' : 'Record leftovers'),
              ),
              if (measured.isEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Text(
                    'No dish has a confirmed prep quantity for $_period on ${friendlyDate(fmtDate(_date))}. '
                    'Confirm the prep first, so there is something to measure the leftover against.',
                    style: TextStyle(color: scheme.onSurfaceVariant),
                  ),
                ),
            ],
          ],
        );
      },
    );
  }
}

class _Note extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String text;

  const _Note({required this.icon, required this.color, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color),
          const SizedBox(width: 10),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}

class _DishRow extends StatelessWidget {
  final Json dish;

  const _DishRow({required this.dish});

  @override
  Widget build(BuildContext context) {
    final confirmed = dish['prep_confirmed'] == true;
    final served = asDouble(dish['served']).round();
    final extra = (dish['sold_beyond_prep'] as num?)?.toInt() ?? 0;
    final percent = (dish['leftover_percent'] as num?)?.toInt();
    final color = !confirmed
        ? Severity.warning
        : (percent != null && percent > 15 ? Severity.critical : Severity.ok);
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      dish['menu_item_name'] as String,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                    ),
                  ),
                  if (!confirmed)
                    SeverityChip(label: 'Prep not confirmed', color: Severity.warning)
                  else
                    SeverityChip(label: '$percent% left', color: color),
                ],
              ),
              const SizedBox(height: 8),
              if (confirmed)
                Row(
                  children: [
                    _Figure(label: 'Prepared', value: trimNum(dish['prepared'])),
                    _Figure(label: 'Served', value: '$served'),
                    _Figure(label: 'Left over', value: trimNum(dish['leftover'])),
                  ],
                )
              else
                Text(
                  'Confirm the prep in Prep to measure this dish. $served served so far.',
                  style: TextStyle(color: muted),
                ),
              if (confirmed && extra > 0)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text('$extra more served than prepared.', style: TextStyle(color: muted)),
                ),
              if (dish['recorded'] == true)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Row(
                    children: [
                      Icon(Icons.check_circle_rounded, size: 16, color: Severity.ok),
                      const SizedBox(width: 6),
                      Text('Recorded', style: TextStyle(color: muted)),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Figure extends StatelessWidget {
  final String label;
  final String value;

  const _Figure({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}
