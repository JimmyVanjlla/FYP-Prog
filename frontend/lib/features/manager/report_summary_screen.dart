import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

// The report PDF's fixed categorical pair (Ch4 section 4.7.2, principle 03):
// the same colour always means the same series, here and in the PDF.
const _leftoverColor = Color(0xFF1565C0);
const _expiryColor = Color(0xFFEF6C00);

/// One day of the forecast-accuracy table: totals across every dish and meal
/// period scored that day.
class _Day {
  final DateTime date;
  double predicted = 0;
  double actual = 0;
  double errorSum = 0;
  int count = 0;

  _Day(this.date);

  double get meanError => count == 0 ? 0 : errorSum / count;
}

/// One dish's average forecast error over the period.
class _DishError {
  final String name;
  final double meanError;
  final int count;

  const _DishError(this.name, this.meanError, this.count);
}

/// What the report screen needs, worked out once from the API's figures.
class _ReportData {
  final Json report;
  final List<_Day> days;
  final List<_DishError> dishes; // worst first

  _ReportData(this.report, this.days, this.dishes);

  static _ReportData from(Json report, Map<int, String> dishNames) {
    final rows = asJsonList(asJson(report['forecast_accuracy'])['rows']);
    final byDay = <String, _Day>{};
    final byDish = <int, List<double>>{};
    for (final r in rows) {
      final date = parseDate(r['forecast_date']);
      if (date == null) continue;
      final day = byDay.putIfAbsent(fmtDate(date), () => _Day(date));
      final error = asDouble(r['error']);
      day.predicted += asDouble(r['predicted']);
      day.actual += asDouble(r['actual']);
      day.errorSum += error;
      day.count++;
      byDish.putIfAbsent(r['menu_item_id'] as int, () => []).add(error);
    }
    final days = byDay.values.toList()
      ..sort((a, b) => a.date.compareTo(b.date));
    final dishes = [
      for (final e in byDish.entries)
        _DishError(
          dishNames[e.key] ?? 'Menu item #${e.key}',
          e.value.reduce((a, b) => a + b) / e.value.length,
          e.value.length,
        ),
    ]..sort((a, b) => b.meanError.compareTo(a.meanError));
    return _ReportData(report, days, dishes);
  }
}

String _pct(double fraction) => '${(fraction * 100).toStringAsFixed(1)}%';

/// UC-RA-01 — a weekly report read in the app. It is laid out like a report
/// rather than a list of figures: a header with the period, the headline
/// numbers, a short written summary, then the same three sections the PDF
/// holds in the same order (forecast accuracy, waste, budget), with the PDF a
/// tap away and, if generation failed, a Regenerate action.
class ReportSummaryScreen extends StatefulWidget {
  final int reportId;

  const ReportSummaryScreen({super.key, required this.reportId});

  @override
  State<ReportSummaryScreen> createState() => _ReportSummaryScreenState();
}

class _ReportSummaryScreenState extends State<ReportSummaryScreen> {
  int _version = 0;
  bool _regenerating = false;

  Future<void> _openPdf() async {
    final auth = context.read<AuthState>();
    final token = auth.token;
    if (token == null) return;
    await launchUrl(
      auth.api.reportDownloadUrl(widget.reportId, token: token),
      mode: LaunchMode.externalApplication,
    );
  }

  Future<void> _regenerate() async {
    setState(() => _regenerating = true);
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/reports/${widget.reportId}/regenerate'),
      success: 'Report regenerated.',
    );
    if (!mounted) return;
    setState(() {
      _regenerating = false;
      if (ok) _version++;
    });
  }

  Future<_ReportData> _load() async {
    final api = context.read<AuthState>().api;
    final results = await Future.wait([
      api.getJson('/reports/${widget.reportId}/summary'),
      api.getJson(
        '/menu-items',
        query: {'include_inactive': true, 'limit': 500},
      ),
    ]);
    final names = {
      for (final m in asJsonList(results[1]))
        m['menu_item_id'] as int: m['name'] as String,
    };
    return _ReportData.from(asJson(results[0]), names);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Weekly report')),
      body: AsyncView<_ReportData>(
        key: ValueKey(_version),
        load: _load,
        builder: (context, data, reload) {
          final report = data.report;
          final failed = report['status'] == 'failed';
          final accuracy = asJson(report['forecast_accuracy']);
          final waste = asJson(report['waste']);
          final budget = asJson(report['budget']);
          final meanError = accuracy['mean_error'] == null
              ? null
              : asDouble(accuracy['mean_error']);

          final leftover = asDouble(waste['leftover_cost']);
          final expiry = asDouble(waste['expiry_cost']);
          final wasteTotal = leftover + expiry;
          final spent = asDouble(budget['spent']);
          final limit = asDouble(budget['limit']);
          final pct = asDouble(budget['utilisation_pct']);
          final budgetColor = pct >= 100
              ? Severity.critical
              : (pct >= 80 ? Severity.warning : Severity.ok);

          return RefreshableList(
            onRefresh: reload,
            children: [
              _Header(
                report: report,
                failed: failed,
                regenerating: _regenerating,
                onOpenPdf: _openPdf,
                onRegenerate: _regenerate,
              ),
              const SizedBox(height: 16),
              IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      child: StatTile(
                        icon: Icons.track_changes_rounded,
                        value: meanError == null ? 'n/a' : _pct(meanError),
                        label: 'Average forecast error',
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: StatTile(
                        icon: Icons.delete_outline_rounded,
                        value: 'RM ${wasteTotal.toStringAsFixed(0)}',
                        label: 'Waste cost',
                        color: _expiryColor,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: StatTile(
                        icon: Icons.account_balance_wallet_outlined,
                        value: '${pct.toStringAsFixed(0)}%',
                        label: 'Budget used',
                        color: budgetColor,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              _Highlights(
                data: data,
                meanError: meanError,
                scored: accuracy['scored_forecasts'] as int? ?? 0,
                wasteTotal: wasteTotal,
                leftover: leftover,
                logCount: waste['log_count'] as int? ?? 0,
                spent: spent,
                limit: limit,
                pct: pct,
              ),
              const SizedBox(height: 22),
              const SectionHeader(
                icon: Icons.track_changes_rounded,
                label: '1. Forecast accuracy',
              ),
              _ForecastSection(data: data),
              const SizedBox(height: 22),
              const SectionHeader(
                icon: Icons.delete_outline_rounded,
                label: '2. Waste cost',
                color: _expiryColor,
              ),
              _WasteSection(
                leftover: leftover,
                expiry: expiry,
                logCount: waste['log_count'] as int? ?? 0,
              ),
              const SizedBox(height: 22),
              const SectionHeader(
                icon: Icons.pie_chart_outline_rounded,
                label: '3. Leftover calculation',
              ),
              _LeftoverSection(leftover: report['leftover'] is Map ? asJson(report['leftover']) : <String, dynamic>{}),
              const SizedBox(height: 22),
              const SectionHeader(
                icon: Icons.groups_rounded,
                label: '4. Staff assignment',
              ),
              _StaffingSection(shifts: report['staffing'] is List ? asJsonList(report['staffing']) : const []),
              const SizedBox(height: 22),
              SectionHeader(
                icon: Icons.account_balance_wallet_outlined,
                label: '5. Budget utilisation',
                color: budgetColor,
              ),
              _BudgetSection(
                spent: spent,
                limit: limit,
                pct: pct,
                color: budgetColor,
              ),
              const SizedBox(height: 22),
              _Footer(report: report),
            ],
          );
        },
      ),
    );
  }
}

/// The title block: what this is, which period, when it was made, and the PDF.
class _Header extends StatelessWidget {
  final Json report;
  final bool failed;
  final bool regenerating;
  final VoidCallback onOpenPdf;
  final VoidCallback onRegenerate;

  const _Header({
    required this.report,
    required this.failed,
    required this.regenerating,
    required this.onOpenPdf,
    required this.onRegenerate,
  });

  @override
  Widget build(BuildContext context) {
    final generated = report['generated_at'];
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: brandGradient(context),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'WEEKLY REPORT',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.85),
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.2,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '${friendlyDate(report['period_start'])} to ${friendlyDate(report['period_end'])}',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Report #${report['report_id']}${generated == null ? '' : '  ·  generated ${friendlyDateTime(generated)}'}',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.85),
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 16),
          if (failed) ...[
            const Text(
              'The PDF for this report could not be generated.',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Theme.of(context).colorScheme.primary,
              ),
              onPressed: regenerating ? null : onRegenerate,
              icon: regenerating
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh_rounded),
              label: const Text('Regenerate report'),
            ),
          ] else
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Theme.of(context).colorScheme.primary,
              ),
              onPressed: onOpenPdf,
              icon: const Icon(Icons.picture_as_pdf_rounded),
              label: const Text('Open PDF'),
            ),
        ],
      ),
    );
  }
}

/// The report in a few sentences, so a reader gets the point before the detail.
class _Highlights extends StatelessWidget {
  final _ReportData data;
  final double? meanError;
  final int scored;
  final double wasteTotal;
  final double leftover;
  final int logCount;
  final double spent;
  final double limit;
  final double pct;

  const _Highlights({
    required this.data,
    required this.meanError,
    required this.scored,
    required this.wasteTotal,
    required this.leftover,
    required this.logCount,
    required this.spent,
    required this.limit,
    required this.pct,
  });

  @override
  Widget build(BuildContext context) {
    final lines = <String>[];
    if (meanError == null) {
      lines.add('No forecasts were scored in this period.');
    } else {
      var line =
          'Forecasts were off by ${_pct(meanError!)} on average across $scored scored forecasts.';
      if (data.dishes.length >= 2) {
        line +=
            ' Closest: ${data.dishes.last.name} (${_pct(data.dishes.last.meanError)}); '
            'furthest: ${data.dishes.first.name} (${_pct(data.dishes.first.meanError)}).';
      }
      lines.add(line);
    }
    if (logCount == 0) {
      lines.add('No waste was recorded.');
    } else {
      final share = wasteTotal == 0 ? 0 : (leftover / wasteTotal * 100).round();
      lines.add(
        '${money(wasteTotal)} of food was wasted across $logCount entries, $share% of it leftovers.',
      );
    }
    lines.add(
      '${money(spent)} was ordered against the ${money(limit)} monthly budget (${pct.toStringAsFixed(0)}%); '
      '${money(limit - spent)} remains.',
    );

    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'In summary',
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            for (final l in lines)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 7, right: 10),
                      child: Container(
                        width: 6,
                        height: 6,
                        decoration: BoxDecoration(
                          color: scheme.primary,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        l,
                        style: Theme.of(context).textTheme.bodyMedium,
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

/// Day-by-day totals as a table, then each dish's average error as a ranked bar.
class _ForecastSection extends StatelessWidget {
  final _ReportData data;

  const _ForecastSection({required this.data});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (data.days.isEmpty) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text('No forecasts were scored in this period.'),
        ),
      );
    }
    final worst = data.dishes.isEmpty
        ? 1.0
        : data.dishes.first.meanError.clamp(0.01, double.infinity);
    final head = Theme.of(context).textTheme.labelMedium?.copyWith(
      fontWeight: FontWeight.w800,
      color: scheme.onSurfaceVariant,
    );
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'By day, all dishes',
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 10),
            Table(
              columnWidths: const {
                0: FlexColumnWidth(2.2),
                1: FlexColumnWidth(1.4),
                2: FlexColumnWidth(1.2),
                3: FlexColumnWidth(1.2),
              },
              children: [
                TableRow(
                  decoration: BoxDecoration(
                    color: scheme.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  children: [
                    _cell(Text('Date', style: head)),
                    _cell(
                      Text(
                        'Predicted',
                        style: head,
                        textAlign: TextAlign.right,
                      ),
                    ),
                    _cell(
                      Text('Actual', style: head, textAlign: TextAlign.right),
                    ),
                    _cell(
                      Text('Error', style: head, textAlign: TextAlign.right),
                    ),
                  ],
                ),
                for (final d in data.days)
                  TableRow(
                    children: [
                      _cell(Text(friendlyDate(d.date.toIso8601String()))),
                      _cell(
                        Text(
                          d.predicted.round().toString(),
                          textAlign: TextAlign.right,
                        ),
                      ),
                      _cell(
                        Text(
                          d.actual.round().toString(),
                          textAlign: TextAlign.right,
                        ),
                      ),
                      _cell(
                        Text(
                          _pct(d.meanError),
                          textAlign: TextAlign.right,
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              'Portions, summed over every dish and meal period.',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 20),
            Text(
              'By dish, furthest off first',
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 10),
            for (final d in data.dishes)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            d.name,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                        ),
                        Text(
                          _pct(d.meanError),
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: LinearProgressIndicator(
                        value: (d.meanError / worst).clamp(0.0, 1.0),
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

  static Widget _cell(Widget child) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 9),
    child: child,
  );
}

class _WasteSection extends StatelessWidget {
  final double leftover;
  final double expiry;
  final int logCount;

  const _WasteSection({
    required this.leftover,
    required this.expiry,
    required this.logCount,
  });

  @override
  Widget build(BuildContext context) {
    final total = leftover + expiry;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: logCount == 0
            ? Row(
                children: [
                  const Icon(Icons.check_circle_rounded, color: Severity.ok),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'No waste was recorded in this period.',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ),
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${money(total)} across $logCount waste entries',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (total > 0)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: SizedBox(
                        height: 12,
                        child: Row(
                          children: [
                            if (leftover > 0)
                              Expanded(
                                flex: (leftover * 1000).round(),
                                child: Container(color: _leftoverColor),
                              ),
                            if (expiry > 0)
                              Expanded(
                                flex: (expiry * 1000).round(),
                                child: Container(color: _expiryColor),
                              ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 10),
                  _Legend(
                    color: _leftoverColor,
                    label: 'Leftovers',
                    value: money(leftover),
                  ),
                  _Legend(
                    color: _expiryColor,
                    label: 'Expired stock',
                    value: money(expiry),
                  ),
                ],
              ),
      ),
    );
  }
}

class _BudgetSection extends StatelessWidget {
  final double spent;
  final double limit;
  final double pct;
  final Color color;

  const _BudgetSection({
    required this.spent,
    required this.limit,
    required this.pct,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${money(spent)} of ${money(limit)}',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                SeverityChip(
                  label: '${pct.toStringAsFixed(0)}% used',
                  color: color,
                ),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: (pct / 100).clamp(0.0, 1.0),
                minHeight: 10,
                color: color,
                backgroundColor: color.withValues(alpha: 0.12),
              ),
            ),
            const SizedBox(height: 10),
            _Legend(
              color: color,
              label: 'Ordered this period',
              value: money(spent),
            ),
            _Legend(
              color: Theme.of(context).colorScheme.outline,
              label: 'Remaining of monthly limit',
              value: money(limit - spent),
            ),
          ],
        ),
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  final Json report;

  const _Footer({required this.report});

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.bodySmall?.copyWith(
      color: Theme.of(context).colorScheme.onSurfaceVariant,
    );
    return Column(
      children: [
        Text(
          'Restaurant Ops  ·  Weekly report #${report['report_id']}',
          style: style?.copyWith(fontWeight: FontWeight.w700),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 2),
        Text(
          'Forecast error is the average of |predicted - actual| / actual. Budget is the month\'s limit; '
          'spend counts purchase orders raised in the period.',
          style: style,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
      ],
    );
  }
}

class _Legend extends StatelessWidget {
  final Color color;
  final String label;
  final String value;

  const _Legend({
    required this.color,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Expanded(child: Text(label)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}


/// The % leftover calculation: leftover = confirmed prep - portions served,
/// over the period, overall and dish by dish (highest share first).
class _LeftoverSection extends StatelessWidget {
  final Json leftover;

  const _LeftoverSection({required this.leftover});

  @override
  Widget build(BuildContext context) {
    final dishes = leftover['dishes'] is List ? asJsonList(leftover['dishes']) : const <Json>[];
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    if (dishes.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 6),
        child: Text('No leftovers were recorded in this period.'),
      );
    }
    final percent = asDouble(leftover['leftover_percent']);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${percent.toStringAsFixed(1)}% of what was prepared was left over',
              style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
            ),
            Text(
              '${asDouble(leftover['leftover']).round()} of ${asDouble(leftover['prepared']).round()} portions; '
              '${asDouble(leftover['served']).round()} served.',
              style: TextStyle(color: muted),
            ),
            const SizedBox(height: 12),
            for (final d in dishes.take(8))
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(child: Text(d['menu_item_name'] as String)),
                        Text(
                          '${asDouble(d['leftover']).round()} of ${asDouble(d['prepared']).round()}  ·  '
                          '${asDouble(d['leftover_percent']).toStringAsFixed(1)}%',
                          style: TextStyle(color: muted),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: (asDouble(d['leftover_percent']) / 100).clamp(0.0, 1.0),
                        minHeight: 6,
                        color: asDouble(d['leftover_percent']) > 15 ? Severity.critical : Severity.ok,
                      ),
                    ),
                  ],
                ),
              ),
            Text(
              'Leftover = confirmed prep minus the portions served (completed orders).',
              style: TextStyle(color: muted, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

/// Who was assigned to which duty: each published shift in the period.
class _StaffingSection extends StatelessWidget {
  final List<Json> shifts;

  const _StaffingSection({required this.shifts});

  @override
  Widget build(BuildContext context) {
    if (shifts.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 6),
        child: Text('No shifts were published in this period.'),
      );
    }
    return Column(
      children: [
        for (final shift in shifts.take(14))
          Card(
            child: ListTile(
              dense: true,
              leading: const IconBadge(icon: Icons.event_available_rounded),
              title: Text('${friendlyDate(shift['date'])}  ·  ${shift['meal_period']}'),
              subtitle: Text(
                () {
                  final staff = asJsonList(shift['staff']);
                  if (staff.isEmpty) return 'No one assigned.';
                  return staff.map((p) => '${p['name']} (${p['station']})').join(', ');
                }(),
              ),
            ),
          ),
        if (shifts.length > 14)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('and ${shifts.length - 14} more shifts.'),
          ),
      ],
    );
  }
}
