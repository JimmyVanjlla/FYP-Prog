import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
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
    setState(() => _future = _load());
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
              else
                for (final t in data.trends) ...[
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
