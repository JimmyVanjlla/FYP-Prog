import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/format.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';

/// UC-DF-01 — demand forecasts by menu item, meal period and date, with a
/// plain explanation (and the minimum-data threshold) wherever a forecast
/// isn't available yet (FR4.6), and the predicted-vs-actual accuracy record
/// (FR4.4). Read-only for everyone; only the Manager can retrain on demand.
class ForecastDashboardScreen extends StatelessWidget {
  const ForecastDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const DefaultTabController(
      length: 2,
      child: Column(
        children: [
          TabBar(
            tabs: [
              Tab(icon: Icon(Icons.insights_rounded), text: 'Forecasts'),
              Tab(icon: Icon(Icons.rule_rounded), text: 'Accuracy'),
            ],
          ),
          Expanded(child: TabBarView(children: [_ForecastsTab(), _AccuracyTab()])),
        ],
      ),
    );
  }
}

class _ForecastData {
  final List<Json> forecasts;
  final List<Json> availability;
  final Map<int, String> itemNames;

  _ForecastData(this.forecasts, this.availability, this.itemNames);
}

class _ForecastsTab extends StatefulWidget {
  const _ForecastsTab();

  @override
  State<_ForecastsTab> createState() => _ForecastsTabState();
}

class _ForecastsTabState extends State<_ForecastsTab> {
  int? _itemId;
  String? _mealPeriod;
  late DateTimeRange _range;
  int _loadCount = 0;
  bool _training = false;

  @override
  void initState() {
    super.initState();
    final today = DateTime.now();
    _range = DateTimeRange(start: today, end: today.add(const Duration(days: 7)));
  }

  Future<_ForecastData> _load() async {
    final api = context.read<AuthState>().api;
    final results = await Future.wait([
      api.getJson('/forecasting/forecasts', query: {
        'menu_item_id': _itemId,
        'meal_period': _mealPeriod,
        'date_from': fmtDate(_range.start),
        'date_to': fmtDate(_range.end),
        'limit': 500,
      }),
      api.getJson('/forecasting/availability', query: {'menu_item_id': _itemId}),
      api.getJson('/menu-items', query: {'limit': 500}),
    ]);
    final items = asJsonList(results[2]);
    return _ForecastData(
      asJsonList(results[0]),
      asJsonList(results[1]),
      {for (final i in items) i['menu_item_id'] as int: i['name'] as String},
    );
  }

  Future<void> _retrain() async {
    setState(() => _training = true);
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/forecasting/train'),
      success: 'Forecasts updated.',
    );
    if (!mounted) return;
    setState(() {
      _training = false;
      if (ok) _loadCount++;
    });
  }

  @override
  Widget build(BuildContext context) {
    final isManager = context.read<AuthState>().role == Roles.manager;
    return AsyncView<_ForecastData>(
      key: ValueKey('$_loadCount|$_itemId|$_mealPeriod|${_range.start}|${_range.end}'),
      load: _load,
      builder: (context, data, reload) {
        final byDate = <String, List<Json>>{};
        for (final f in data.forecasts) {
          byDate.putIfAbsent(f['forecast_date'] as String, () => []).add(f);
        }
        final dates = byDate.keys.toList()..sort();
        final peak = data.forecasts.fold<double>(1, (m, f) {
          final v = asDouble(f['predicted_quantity']);
          return v > m ? v : m;
        });
        final unavailable = data.availability.where((a) => a['available'] != true).toList();

        return RefreshableList(
          onRefresh: reload,
          children: [
            _Filters(
              itemNames: data.itemNames,
              itemId: _itemId,
              mealPeriod: _mealPeriod,
              range: _range,
              onItem: (v) => setState(() => _itemId = v),
              onPeriod: (v) => setState(() => _mealPeriod = v),
              onRange: (v) => setState(() => _range = v),
            ),
            if (isManager) ...[
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _training ? null : _retrain,
                icon: _training
                    ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.model_training_rounded),
                label: Text(_training ? 'Retraining (this can take a minute)...' : 'Retrain forecasts now'),
              ),
            ],
            if (unavailable.isNotEmpty) ...[
              const SizedBox(height: 16),
              _UnavailableCard(items: unavailable),
            ],
            const SizedBox(height: 16),
            if (dates.isEmpty)
              const EmptyState(
                icon: Icons.query_stats_rounded,
                message: 'No forecasts in this range.',
                detail: 'Try a wider date range, or see the note above for items still gathering history.',
              ),
            for (final d in dates) ...[
              SectionHeader(icon: Icons.event_rounded, label: friendlyDate(d)),
              for (final f in byDate[d]!)
                _ForecastRow(
                  name: data.itemNames[f['menu_item_id']] ?? 'Item #${f['menu_item_id']}',
                  period: f['meal_period'] as String,
                  quantity: asDouble(f['predicted_quantity']),
                  peak: peak,
                ),
              const SizedBox(height: 14),
            ],
          ],
        );
      },
    );
  }
}

class _Filters extends StatelessWidget {
  final Map<int, String> itemNames;
  final int? itemId;
  final String? mealPeriod;
  final DateTimeRange range;
  final ValueChanged<int?> onItem;
  final ValueChanged<String?> onPeriod;
  final ValueChanged<DateTimeRange> onRange;

  const _Filters({
    required this.itemNames,
    required this.itemId,
    required this.mealPeriod,
    required this.range,
    required this.onItem,
    required this.onPeriod,
    required this.onRange,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        DropdownButtonFormField<int?>(
          isExpanded: true,
          initialValue: itemId,
          decoration: const InputDecoration(labelText: 'Menu item'),
          items: [
            const DropdownMenuItem<int?>(value: null, child: Text('All items')),
            for (final e in itemNames.entries) DropdownMenuItem<int?>(value: e.key, child: Text(e.value)),
          ],
          onChanged: onItem,
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: DropdownButtonFormField<String?>(
                isExpanded: true,
                initialValue: mealPeriod,
                decoration: const InputDecoration(labelText: 'Meal period'),
                items: [
                  const DropdownMenuItem<String?>(value: null, child: Text('All')),
                  for (final p in mealPeriods) DropdownMenuItem<String?>(value: p, child: Text(p)),
                ],
                onChanged: onPeriod,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton.icon(
                icon: const Icon(Icons.date_range_rounded),
                label: Text(
                  '${shortDate(fmtDate(range.start))} - ${shortDate(fmtDate(range.end))}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                onPressed: () async {
                  final picked = await showDateRangePicker(
                    context: context,
                    firstDate: DateTime.now().subtract(const Duration(days: 365)),
                    lastDate: DateTime.now().add(const Duration(days: 365)),
                    initialDateRange: range,
                  );
                  if (picked != null) onRange(picked);
                },
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _UnavailableCard extends StatelessWidget {
  final List<Json> items;

  const _UnavailableCard({required this.items});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Severity.warning.withValues(alpha: 0.10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.info_rounded, color: Severity.warning, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${items.length} item${items.length == 1 ? '' : 's'} without a forecast yet',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            for (final a in items.take(8))
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(a['message'] as String, style: Theme.of(context).textTheme.bodySmall),
              ),
            if (items.length > 8)
              Text('...and ${items.length - 8} more.', style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _ForecastRow extends StatelessWidget {
  final String name;
  final String period;
  final double quantity;
  final double peak;

  const _ForecastRow({required this.name, required this.period, required this.quantity, required this.peak});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('$name  ·  $period', style: Theme.of(context).textTheme.titleSmall),
                  ),
                  Text(
                    '${trimNum(quantity)} portions',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: peak == 0 ? 0 : (quantity / peak).clamp(0.0, 1.0),
                  minHeight: 8,
                  backgroundColor: scheme.surfaceContainerHighest,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AccuracyTab extends StatelessWidget {
  const _AccuracyTab();

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<({List<Json> rows, Map<int, String> names})>(
      load: () async {
        final rows = asJsonList(await api.getJson('/forecasting/accuracy', query: {'limit': 200}));
        final items = asJsonList(await api.getJson('/menu-items', query: {'limit': 500}));
        return (rows: rows, names: {for (final i in items) i['menu_item_id'] as int: i['name'] as String});
      },
      builder: (context, data, reload) {
        final errors = data.rows.map((r) => asDouble(r['accuracy_error'])).toList();
        final mean = errors.isEmpty ? 0.0 : errors.reduce((a, b) => a + b) / errors.length;
        return RefreshableList(
          onRefresh: reload,
          empty: const EmptyState(
            icon: Icons.rule_rounded,
            message: 'No accuracy records yet.',
            detail: 'Once a forecast date has passed and its real orders are logged, '
                'predicted vs actual shows up here.',
          ),
          children: [
            if (data.rows.isNotEmpty) ...[
              Card(
                child: ListTile(
                  leading: const IconBadge(icon: Icons.track_changes_rounded),
                  title: Text('Average error ${(mean * 100).toStringAsFixed(1)}%'),
                  subtitle: Text('Across ${data.rows.length} scored forecasts'),
                  trailing: SeverityChip(
                    label: mean <= 0.15 ? 'On track' : (mean <= 0.30 ? 'Fair' : 'Review'),
                    color: mean <= 0.15 ? Severity.ok : (mean <= 0.30 ? Severity.warning : Severity.critical),
                  ),
                ),
              ),
              const SizedBox(height: 12),
            ],
            for (final r in data.rows)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Card(
                  child: ListTile(
                    dense: true,
                    title: Text(
                      '${data.names[r['menu_item_id']] ?? 'Item #${r['menu_item_id']}'}  ·  ${r['meal_period']}',
                    ),
                    subtitle: Text(
                      '${friendlyDate(r['forecast_date'])}: predicted ${trimNum(r['predicted_quantity'])}, '
                      'actual ${trimNum(r['actual_quantity'])}',
                    ),
                    trailing: Text('${(asDouble(r['accuracy_error']) * 100).toStringAsFixed(1)}%'),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}
