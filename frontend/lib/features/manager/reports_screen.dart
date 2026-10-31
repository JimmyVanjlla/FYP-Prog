import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/theme.dart';
import '../../models/report.dart';
import 'report_summary_screen.dart';

/// Module 11 — FR11.1/FR11.2. Manager triggers a weekly summary and opens
/// the generated PDF in the system viewer (no in-app PDF renderer).
class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  late Future<List<Report>> _future;
  DateTimeRange? _range;
  bool _generating = false;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _range = DateTimeRange(
      start: now.subtract(const Duration(days: 7)),
      end: now,
    );
    _future = _load();
  }

  Future<List<Report>> _load() async {
    final api = context.read<AuthState>().api;
    final raw = await api.listReports();
    return raw.map((e) => Report.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
    await _future;
  }

  String _fmt(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _generate() async {
    if (_range == null) return;
    setState(() => _generating = true);
    try {
      final api = context.read<AuthState>().api;
      await api.generateWeeklyReport(
        periodStart: _fmt(_range!.start),
        periodEnd: _fmt(_range!.end),
      );
      await _refresh();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainer,
            border: Border(
              bottom: BorderSide(
                color: Theme.of(context).colorScheme.outlineVariant.withValues(alpha: 0.4),
              ),
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.date_range),
                  label: Text(
                    _range == null
                        ? 'Pick period'
                        : '${_fmt(_range!.start)} → ${_fmt(_range!.end)}',
                  ),
                  onPressed: () async {
                    final picked = await showDateRangePicker(
                      context: context,
                      firstDate: DateTime(2020),
                      lastDate: DateTime(2100),
                      initialDateRange: _range,
                    );
                    if (picked != null) setState(() => _range = picked);
                  },
                ),
              ),
              const SizedBox(width: 12),
              FilledButton(
                onPressed: _generating ? null : _generate,
                child: _generating
                    ? const SizedBox(
                        height: 16,
                        width: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Generate'),
              ),
            ],
          ),
        ),
        Expanded(
          child: FutureBuilder<List<Report>>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }
              final reports = snapshot.data ?? [];
              if (reports.isEmpty) {
                return const EmptyState(
                  icon: Icons.description_outlined,
                  message: 'No reports generated yet.',
                  detail: 'Pick a period above and tap Generate.',
                );
              }
              return RefreshIndicator(
                onRefresh: _refresh,
                child: ListView.separated(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: reports.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, index) {
                    final report = reports[index];
                    return Card(
                      child: ListTile(
                        leading: IconBadge(
                          icon: Icons.picture_as_pdf_rounded,
                          color: report.status == 'generated'
                              ? Severity.ok
                              : Severity.critical,
                        ),
                        title: Text(
                          '${report.periodStart} → ${report.periodEnd}',
                        ),
                        subtitle: Text(report.type),
                        trailing: report.status == 'generated'
                            ? SeverityChip(
                                label: 'View',
                                color: Severity.ok,
                              )
                            : SeverityChip(
                                label: 'Failed',
                                color: Severity.critical,
                              ),
                        onTap: () async {
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => ReportSummaryScreen(reportId: report.reportId),
                            ),
                          );
                          if (mounted) await _refresh();
                        },
                      ),
                    );
                  },
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}
