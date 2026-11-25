import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

// The same fixed pair as the weekly report: the same colour always means the
// same source of waste.
const _leftoverColor = Color(0xFF1565C0);
const _expiryColor = Color(0xFFEF6C00);

/// Module 6, FR6.1 / FR6.3. What was wasted and what it cost: this week
/// against last, the last eight weeks as a chart, the biggest sources over the
/// last four weeks (by dish and by ingredient), and the latest entries. The
/// weekly figures are worked out from the waste log each time the screen
/// opens, so they are never out of date.
class WasteScreen extends StatelessWidget {
  const WasteScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<_WasteData>(
      load: () async {
        final logs = await api.listWasteLogs();
        final summary = asJson(await api.getJson('/waste/summary', query: {'weeks': 8}));
        final ingredients = await api.listIngredients();
        // The prediction is an extra; the screen still works without it.
        Json prediction = {};
        try {
          prediction = asJson(await api.getJson('/waste/prediction', query: {'days': 7}));
        } catch (_) {}
        return _WasteData(
          prediction: prediction,
          logs: logs,
          weeks: asJsonList(summary['weeks']),
          topDishes: asJsonList(summary['top_dishes']),
          topIngredients: asJsonList(summary['top_ingredients']),
          ingredients: {for (final i in ingredients) (i as Map<String, dynamic>)['ingredient_id'] as int: i},
        );
      },
      builder: (context, data, reload) {
        final thisWeek = data.weeks.isEmpty ? 0.0 : asDouble(data.weeks.last['total_cost']);
        final lastWeek = data.weeks.length < 2 ? 0.0 : asDouble(data.weeks[data.weeks.length - 2]['total_cost']);
        final change = thisWeek - lastWeek;
        final anyWaste = data.weeks.any((w) => (w['entries'] as int? ?? 0) > 0);
        return RefreshableList(
          onRefresh: reload,
          children: [
            Row(
              children: [
                Expanded(
                  child: StatTile(
                    icon: Icons.delete_outline_rounded,
                    value: 'RM ${thisWeek.toStringAsFixed(0)}',
                    label: 'This week so far',
                    color: _expiryColor,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: StatTile(
                    icon: Icons.history_rounded,
                    value: 'RM ${lastWeek.toStringAsFixed(0)}',
                    label: 'Last week',
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: StatTile(
                    icon: change <= 0 ? Icons.trending_down_rounded : Icons.trending_up_rounded,
                    value: '${change > 0 ? '+' : change < 0 ? '-' : ''}RM ${change.abs().toStringAsFixed(0)}',
                    label: 'Change on last week',
                    color: change <= 0 ? Severity.ok : Severity.critical,
                  ),
                ),
              ],
            ),
            if (data.prediction.isNotEmpty) ...[
              const SizedBox(height: 14),
              _PredictionCard(prediction: data.prediction),
            ],
            const SizedBox(height: 20),
            const SectionHeader(icon: Icons.bar_chart_rounded, label: 'Waste cost by week'),
            if (!anyWaste)
              const EmptyState(
                icon: Icons.show_chart_rounded,
                message: 'No waste recorded in the last eight weeks.',
                detail: 'Leftovers logged by the kitchen and expired stock appear here.',
              )
            else
              _WeekChart(weeks: data.weeks),
            if (data.topDishes.isNotEmpty) ...[
              const SizedBox(height: 20),
              const SectionHeader(icon: Icons.restaurant_menu_rounded, label: 'Most wasted dishes, last 4 weeks'),
              _RankedBars(
                rows: [for (final d in data.topDishes) (name: d['name'] as String, detail: null, cost: asDouble(d['cost']))],
              ),
            ],
            if (data.topIngredients.isNotEmpty) ...[
              const SizedBox(height: 20),
              const SectionHeader(icon: Icons.inventory_2_rounded, label: 'Most wasted ingredients, last 4 weeks'),
              _RankedBars(
                rows: [
                  for (final i in data.topIngredients)
                    (name: i['name'] as String, detail: '${trimNum(i['quantity'])} ${i['unit']}', cost: asDouble(i['cost'])),
                ],
              ),
            ],
            const SizedBox(height: 20),
            const SectionHeader(icon: Icons.delete_outline_rounded, label: 'Recent waste log'),
            if (data.logs.isEmpty)
              const EmptyState(icon: Icons.delete_sweep_outlined, message: 'No waste logged yet.')
            else
              for (final log in data.logs.take(25)) ...[
                Card(
                  child: ListTile(
                    leading: IconBadge(
                      icon: Icons.delete_outline_rounded,
                      color: log['source_type'] == 'expiry' ? _expiryColor : _leftoverColor,
                    ),
                    title: Text(
                      '${data.ingredients[log['ingredient_id']]?['name'] ?? 'Ingredient #${log['ingredient_id']}'}'
                      '  ·  ${log['source_type'] == 'expiry' ? 'expired' : 'leftover'}',
                    ),
                    subtitle: Text(
                      '${trimNum(log['quantity_wasted'])} ${data.ingredients[log['ingredient_id']]?['unit'] ?? ''} wasted'
                      '  ·  ${friendlyDate(log['logged_at'])}',
                    ),
                    trailing: Text('RM ${log['waste_cost']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ),
                const SizedBox(height: 8),
              ],
          ],
        );
      },
    );
  }
}

class _WasteData {
  final Json prediction;
  final List<dynamic> logs;
  final List<Json> weeks;
  final List<Json> topDishes;
  final List<Json> topIngredients;
  final Map<int, dynamic> ingredients;

  _WasteData({
    required this.prediction,
    required this.logs,
    required this.weeks,
    required this.topDishes,
    required this.topIngredients,
    required this.ingredients,
  });
}

/// Waste cost per week, oldest to newest, each bar split into leftovers and
/// expired stock. Drawn with plain widgets so it needs no chart package.
class _WeekChart extends StatelessWidget {
  final List<Json> weeks;

  const _WeekChart({required this.weeks});

  @override
  Widget build(BuildContext context) {
    final peak = weeks.fold<double>(0, (m, w) => asDouble(w['total_cost']) > m ? asDouble(w['total_cost']) : m);
    final scheme = Theme.of(context).colorScheme;
    const barArea = 100.0;
    final small = Theme.of(context).textTheme.labelSmall;
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 14, 12, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              height: barArea + 28,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  for (final w in weeks)
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 3),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            Text(asDouble(w['total_cost']) == 0 ? '' : asDouble(w['total_cost']).toStringAsFixed(0), style: small),
                            const SizedBox(height: 4),
                            ClipRRect(
                              borderRadius: const BorderRadius.vertical(top: Radius.circular(5)),
                              child: SizedBox(
                                height: peak == 0 ? 2 : (asDouble(w['total_cost']) / peak * barArea).clamp(2.0, barArea),
                                child: Column(
                                  children: [
                                    if (asDouble(w['expiry_cost']) > 0)
                                      Expanded(
                                        flex: (asDouble(w['expiry_cost']) * 100).round(),
                                        child: Container(color: _expiryColor),
                                      ),
                                    Expanded(
                                      flex: (asDouble(w['leftover_cost']) * 100).round().clamp(1, 1 << 30),
                                      child: Container(color: asDouble(w['total_cost']) == 0 ? scheme.outlineVariant : _leftoverColor),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                for (final w in weeks)
                  Expanded(
                    child: Text(
                      shortDate(w['period_start']),
                      textAlign: TextAlign.center,
                      style: small?.copyWith(color: scheme.onSurfaceVariant),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text('Weeks start on Monday. RM per week.', style: small?.copyWith(color: scheme.onSurfaceVariant)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 16,
              children: const [
                _Dot(color: _leftoverColor, label: 'Leftovers'),
                _Dot(color: _expiryColor, label: 'Expired stock'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  final Color color;
  final String label;

  const _Dot({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}

/// Names ranked by cost, each with a bar sized against the biggest.
class _RankedBars extends StatelessWidget {
  final List<({String name, String? detail, double cost})> rows;

  const _RankedBars({required this.rows});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final peak = rows.fold<double>(0, (m, r) => r.cost > m ? r.cost : m);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          children: [
            for (final r in rows)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(child: Text(r.name, style: const TextStyle(fontWeight: FontWeight.w600))),
                        if (r.detail != null)
                          Padding(
                            padding: const EdgeInsets.only(right: 10),
                            child: Text(r.detail!, style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12)),
                          ),
                        Text(money(r.cost), style: const TextStyle(fontWeight: FontWeight.w800)),
                      ],
                    ),
                    const SizedBox(height: 4),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: LinearProgressIndicator(
                        value: peak == 0 ? 0 : (r.cost / peak).clamp(0.0, 1.0),
                        minHeight: 8,
                        color: scheme.primary,
                        backgroundColor: scheme.primary.withValues(alpha: 0.10),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}


/// What the next week is expected to waste: the forecast portions times the share
/// the kitchen has recently been left with, costed from the recipes.
class _PredictionCard extends StatelessWidget {
  final Json prediction;

  const _PredictionCard({required this.prediction});

  @override
  Widget build(BuildContext context) {
    final dishes = asJsonList(prediction['dishes']);
    final total = asDouble(prediction['total_cost']);
    final portions = asDouble(prediction['total_portions']);
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const IconBadge(icon: Icons.query_stats_rounded),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Expected waste, next 7 days',
                          style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                      Text(
                        dishes.isEmpty
                            ? 'Nothing expected: no dish has had leftovers recently.'
                            : 'About ${portions.round()} portions, from the forecast and recent leftovers.',
                        style: TextStyle(color: muted, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                Text('RM ${total.toStringAsFixed(2)}',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
              ],
            ),
            if (dishes.isNotEmpty) const SizedBox(height: 10),
            for (final d in dishes.take(3))
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(
                  children: [
                    Expanded(child: Text(d['menu_item_name'] as String)),
                    Text(
                      '~${asDouble(d['expected_leftover_portions']).round()} portions  ·  RM ${asDouble(d['expected_cost']).toStringAsFixed(2)}',
                      style: TextStyle(color: muted),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
