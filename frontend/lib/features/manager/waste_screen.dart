import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';

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
              Text(
                'Waste reduction trend',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              if (data.trends.isEmpty)
                const Text('No trend rollups yet.')
              else
                for (final t in data.trends)
                  Card(
                    child: ListTile(
                      title: Text('${t['period_start']} → ${t['period_end']}'),
                      trailing: Text('RM ${t['total_waste_cost']}'),
                    ),
                  ),
              const SizedBox(height: 24),
              Text(
                'Recent waste log',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              if (data.logs.isEmpty)
                const Text('No waste logged yet.')
              else
                for (final log in data.logs.take(25))
                  Card(
                    child: ListTile(
                      title: Text(
                        'Ingredient #${log['ingredient_id']} — ${log['source_type']}',
                      ),
                      subtitle: Text('${log['quantity_wasted']} wasted'),
                      trailing: Text('RM ${log['waste_cost']}'),
                    ),
                  ),
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
