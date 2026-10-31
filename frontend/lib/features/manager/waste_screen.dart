import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// Module 6 — FR6.1/FR6.3. Read-only waste log + trend view for the
/// Manager; trend rollups themselves are generated via POST
/// /waste/trends (Celery-adjacent — triggered on demand from /docs for
/// now, matching Sprint 3's "no new screens" note for that action).
class WasteScreen extends StatefulWidget {
  const WasteScreen({super.key});

  @override
  State<WasteScreen> createState() => _WasteScreenState();
}

class _WasteScreenState extends State<WasteScreen> {
  late Future<_WasteData> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_WasteData> _load() async {
    final api = context.read<AuthState>().api;
    final logs = await api.listWasteLogs();
    final trends = await api.listWasteTrends();
    return _WasteData(logs: logs, trends: trends);
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_WasteData>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          final message = snapshot.error is ApiException
              ? (snapshot.error as ApiException).message
              : 'Failed to load waste data.';
          return Center(child: Text(message));
        }
        final data = snapshot.data!;
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const SectionHeader(
                icon: Icons.trending_down_rounded,
                label: 'Waste reduction trend',
              ),
              if (data.trends.isEmpty)
                const EmptyState(
                  icon: Icons.show_chart_rounded,
                  message: 'No trend rollups yet.',
                  detail: 'Rolls up automatically from the weekly job.',
                )
              else ...[
                _TrendChart(trends: data.trends),
                const SizedBox(height: 12),
                for (final t in data.trends.reversed) ...[
                  Card(
                    child: ListTile(
                      leading: const IconBadge(icon: Icons.trending_down_rounded),
                      title: Text('${t['period_start']} → ${t['period_end']}'),
                      trailing: Text(
                        'RM ${t['total_waste_cost']}',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
              ],
              const SizedBox(height: 20),
              const SectionHeader(
                icon: Icons.delete_outline_rounded,
                label: 'Recent waste log',
              ),
              if (data.logs.isEmpty)
                const EmptyState(
                  icon: Icons.delete_sweep_outlined,
                  message: 'No waste logged yet.',
                )
              else
                for (final log in data.logs.take(25)) ...[
                  Card(
                    child: ListTile(
                      leading: const IconBadge(
                        icon: Icons.delete_outline_rounded,
                        color: Severity.warning,
                      ),
                      title: Text(
                        'Ingredient #${log['ingredient_id']} — ${log['source_type']}',
                      ),
                      subtitle: Text('${log['quantity_wasted']} wasted'),
                      trailing: Text(
                        'RM ${log['waste_cost']}',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
            ],
          ),
        );
      },
    );
  }
}

class _WasteData {
  final List<dynamic> logs;
  final List<dynamic> trends;

  _WasteData({required this.logs, required this.trends});
}


/// FR6.3 — waste cost per period as a bar chart, oldest to newest, with a
/// line saying whether it's heading down (the thing the Manager actually
/// wants to know). Drawn with plain widgets so it needs no chart package.
class _TrendChart extends StatelessWidget {
  final List<dynamic> trends;

  const _TrendChart({required this.trends});

  @override
  Widget build(BuildContext context) {
    final points = [
      for (final t in trends)
        (label: friendlyDate(t['period_start']), value: asDouble(t['total_waste_cost'])),
    ];
    final peak = points.fold<double>(0, (m, p) => p.value > m ? p.value : m);
    final scheme = Theme.of(context).colorScheme;

    String summary = '';
    if (points.length >= 2) {
      final change = points.last.value - points[points.length - 2].value;
      summary = change == 0
          ? 'Unchanged from the previous period.'
          : change < 0
              ? 'Down ${money(-change)} from the previous period.'
              : 'Up ${money(change)} from the previous period.';
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              height: 140,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  for (final p in points)
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 4),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            Text(
                              trimNum(p.value),
                              style: Theme.of(context).textTheme.labelSmall,
                            ),
                            const SizedBox(height: 4),
                            Container(
                              height: peak == 0 ? 2 : (p.value / peak * 90).clamp(2.0, 90.0),
                              decoration: BoxDecoration(
                                color: scheme.primary,
                                borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
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
                for (final p in points)
                  Expanded(
                    child: Text(
                      p.label,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
                    ),
                  ),
              ],
            ),
            if (summary.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(summary, style: const TextStyle(fontWeight: FontWeight.w600)),
            ],
          ],
        ),
      ),
    );
  }
}
