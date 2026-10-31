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

/// UC-RA-01 — a weekly report read in the app: the same three sections the
/// PDF holds, in the same order (forecast accuracy, waste, budget), with the
/// PDF a tap away and, if generation failed, a Regenerate action.
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

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return Scaffold(
      appBar: AppBar(title: const Text('Weekly report')),
      body: AsyncView<Json>(
        key: ValueKey(_version),
        load: () async => asJson(await api.getJson('/reports/${widget.reportId}/summary')),
        builder: (context, report, reload) {
          final failed = report['status'] == 'failed';
          final accuracy = asJson(report['forecast_accuracy']);
          final waste = asJson(report['waste']);
          final budget = asJson(report['budget']);
          final rows = asJsonList(accuracy['rows']);
          final meanError = accuracy['mean_error'];

          final leftover = asDouble(waste['leftover_cost']);
          final expiry = asDouble(waste['expiry_cost']);
          final wasteTotal = leftover + expiry;
          final pct = asDouble(budget['utilisation_pct']);
          final budgetColor = pct >= 100 ? Severity.critical : (pct >= 80 ? Severity.warning : Severity.ok);

          return RefreshableList(
            onRefresh: reload,
            children: [
              Text(
                '${friendlyDate(report['period_start'])} - ${friendlyDate(report['period_end'])}',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 10),
              if (failed)
                Card(
                  color: Severity.critical.withValues(alpha: 0.10),
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'The PDF for this report could not be generated.',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 10),
                        FilledButton.icon(
                          onPressed: _regenerating ? null : _regenerate,
                          icon: _regenerating
                              ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                              : const Icon(Icons.refresh_rounded),
                          label: const Text('Regenerate report'),
                        ),
                      ],
                    ),
                  ),
                )
              else
                OutlinedButton.icon(
                  onPressed: _openPdf,
                  icon: const Icon(Icons.picture_as_pdf_rounded),
                  label: const Text('Open PDF'),
                ),
              const SizedBox(height: 20),
              const SectionHeader(icon: Icons.rule_rounded, label: '1. Forecast accuracy'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        meanError == null
                            ? 'No forecasts were scored in this period.'
                            : 'Average error ${(asDouble(meanError) * 100).toStringAsFixed(1)}% across '
                                '${accuracy['scored_forecasts']} forecasts',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      for (final r in rows.take(8))
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            '${friendlyDate(r['forecast_date'])} ${r['meal_period']}: '
                            'predicted ${trimNum(r['predicted'])}, actual ${trimNum(r['actual'])}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      if (rows.length > 8)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text('...and ${rows.length - 8} more (see the PDF).', style: Theme.of(context).textTheme.bodySmall),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const SectionHeader(icon: Icons.delete_outline_rounded, label: '2. Waste cost'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${money(wasteTotal)} across ${waste['log_count']} waste entries',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 10),
                      if (wasteTotal > 0)
                        ClipRRect(
                          borderRadius: BorderRadius.circular(6),
                          child: SizedBox(
                            height: 10,
                            child: Row(
                              children: [
                                Expanded(flex: (leftover * 1000).round().clamp(0, 1 << 30), child: Container(color: _leftoverColor)),
                                Expanded(flex: (expiry * 1000).round().clamp(0, 1 << 30), child: Container(color: _expiryColor)),
                              ],
                            ),
                          ),
                        ),
                      const SizedBox(height: 8),
                      _Legend(color: _leftoverColor, label: 'Leftovers', value: money(leftover)),
                      _Legend(color: _expiryColor, label: 'Expired stock', value: money(expiry)),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const SectionHeader(icon: Icons.account_balance_wallet_outlined, label: '3. Budget utilisation'),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${money(budget['spent'])} of ${money(budget['limit'])}',
                              style: const TextStyle(fontWeight: FontWeight.w700),
                            ),
                          ),
                          SeverityChip(label: '${pct.toStringAsFixed(0)}% used', color: budgetColor),
                        ],
                      ),
                      const SizedBox(height: 8),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: LinearProgressIndicator(value: (pct / 100).clamp(0.0, 1.0), minHeight: 8, color: budgetColor),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  final Color color;
  final String label;
  final String value;

  const _Legend({required this.color, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 8),
          Expanded(child: Text(label)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
