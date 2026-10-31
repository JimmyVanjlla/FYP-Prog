import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/dialogs.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';

/// The Schedule Builder (Ch4 section 4.4.1): the staffing recommendation and
/// the roster on the *same* screen, so the supervisor sees "recommended 3,
/// assigned 2" while assigning, and the below-recommendation flag appears
/// the moment staff are assigned, before publishing. The recommendation is a
/// default, never a lock: publishing under it is allowed (and logged).
///
/// Once published it carries on through the shift: attendance at opening
/// (FR8.3), then the closing report with actual vs forecast (FR8.4).
class ScheduleBuilderScreen extends StatefulWidget {
  final Json schedule;

  const ScheduleBuilderScreen({super.key, required this.schedule});

  @override
  State<ScheduleBuilderScreen> createState() => _ScheduleBuilderScreenState();
}

class _BuilderData {
  final Json schedule;
  final List<Json> recommendations;
  final List<Json> assignments;
  final Map<int, Json> staff;
  final Json? closingReport;

  _BuilderData(this.schedule, this.recommendations, this.assignments, this.staff, this.closingReport);
}

class _ScheduleBuilderScreenState extends State<ScheduleBuilderScreen> {
  int get _scheduleId => widget.schedule['schedule_id'] as int;

  Future<_BuilderData> _load() async {
    final api = context.read<AuthState>().api;

    // Recommendations are generated on first open; opening again just
    // shows them (the "Refresh" action regenerates from the latest forecast).
    var recs = asJsonList(await api.getJson('/staffing/schedules/$_scheduleId/recommendations'));
    if (recs.isEmpty) {
      recs = asJsonList(await api.postJson('/staffing/schedules/$_scheduleId/recommendations'));
    }

    final results = await Future.wait([
      api.getJson('/staffing/schedules/$_scheduleId/assignments'),
      api.getJson('/staffing/staff'),
      api.getJson('/staffing/schedules'),
    ]);
    final schedules = asJsonList(results[2]);
    final schedule = schedules.firstWhere((s) => s['schedule_id'] == _scheduleId, orElse: () => widget.schedule);

    Json? closing;
    if (schedule['status'] == 'published') {
      try {
        closing = asJson(await api.getJson('/staffing/schedules/$_scheduleId/closing-report'));
      } on ApiException {
        closing = null; // 404: not submitted yet
      }
    }
    return _BuilderData(
      schedule,
      recs,
      asJsonList(results[0]),
      {for (final s in asJsonList(results[1])) s['user_id'] as int: s},
      closing,
    );
  }

  Future<void> _refreshRecommendations(Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/staffing/schedules/$_scheduleId/recommendations'),
      success: 'Recommendations refreshed from the latest forecast.',
    );
    if (ok) await reload();
  }

  Future<void> _assign(BuildContext context, String station, _BuilderData data, Future<void> Function() reload) async {
    final taken = data.assignments.map((a) => a['staff_id']).toSet();
    final available = data.staff.values.where((s) => !taken.contains(s['user_id'])).toList();
    if (available.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Everyone is already on this shift.')),
      );
      return;
    }
    final chosen = await showModalBottomSheet<Json>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.6),
          child: ListView(
            shrinkWrap: true,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Text('Assign to $station', style: Theme.of(context).textTheme.titleMedium),
              ),
              for (final s in available)
                ListTile(
                  leading: const IconBadge(icon: Icons.person_rounded),
                  title: Text(s['name'] as String),
                  subtitle: Text(s['role'] as String),
                  onTap: () => Navigator.pop(context, s),
                ),
            ],
          ),
        ),
      ),
    );
    if (chosen == null || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/staffing/schedules/$_scheduleId/assignments', {
        'staff_id': chosen['user_id'],
        'station': station,
      }),
    );
    if (ok) await reload();
  }

  Future<void> _publish(BuildContext context, _BuilderData data, Future<void> Function() reload) async {
    final short = <String>[];
    for (final r in data.recommendations) {
      final assigned = data.assignments.where((a) => a['station'] == r['station']).length;
      final recommended = r['recommended_staff_count'] as int;
      if (assigned < recommended) short.add('${r['station']}: $assigned of $recommended');
    }
    final proceed = await confirmAction(
      context,
      title: 'Publish this schedule?',
      message: short.isEmpty
          ? 'Everyone assigned will be notified.'
          : 'Below the recommendation at ${short.join(', ')}. The recommendation is only a guide, '
              'so you can publish anyway; the difference is logged. Everyone assigned will be notified.',
      confirmLabel: 'Publish',
    );
    if (!proceed || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/staffing/schedules/$_scheduleId/publish'),
      success: 'Schedule published. Staff have been notified.',
    );
    if (ok) await reload();
  }

  Future<void> _setAttendance(BuildContext context, Json assignment, String status, Future<void> Function() reload) async {
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.patchJson('/staffing/assignments/${assignment['assignment_id']}/attendance', {
        'attendance_status': status,
      }),
    );
    if (ok) await reload();
  }

  Future<void> _closeShift(BuildContext context, Future<void> Function() reload) async {
    final volume = TextEditingController();
    final notes = TextEditingController();
    final formKey = GlobalKey<FormState>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Close the shift'),
        content: Form(
          key: formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: volume,
                autofocus: true,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Actual orders served', suffixText: 'portions'),
                validator: (v) {
                  final n = int.tryParse(v?.trim() ?? '');
                  if (n == null) return 'Enter a whole number.';
                  if (n < 0) return 'Cannot be negative.';
                  return null;
                },
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: notes,
                maxLines: 3,
                decoration: const InputDecoration(labelText: 'Notes (optional)'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              if (formKey.currentState!.validate()) Navigator.pop(context, true);
            },
            child: const Text('Submit'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final api = context.read<AuthState>().api;
    final ok = await runAction(
      context,
      () => api.postJson('/staffing/schedules/$_scheduleId/closing-report', {
        'actual_order_volume': int.parse(volume.text.trim()),
        if (notes.text.trim().isNotEmpty) 'notes': notes.text.trim(),
      }),
      success: 'Closing report submitted.',
    );
    if (ok) await reload();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('${friendlyDate(widget.schedule['date'])}  ·  ${widget.schedule['meal_period']}'),
      ),
      body: AsyncView<_BuilderData>(
        load: _load,
        builder: (context, data, reload) {
          final published = data.schedule['status'] == 'published';
          return RefreshableList(
            onRefresh: reload,
            children: [
              Row(
                children: [
                  SeverityChip(
                    label: published ? 'Published' : 'Draft',
                    color: published ? Severity.ok : Severity.warning,
                  ),
                  const Spacer(),
                  if (!published)
                    TextButton.icon(
                      onPressed: () => _refreshRecommendations(reload),
                      icon: const Icon(Icons.refresh_rounded, size: 18),
                      label: const Text('Refresh'),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              for (final rec in data.recommendations) ...[
                _StationSection(
                  recommendation: rec,
                  assignments: data.assignments.where((a) => a['station'] == rec['station']).toList(),
                  staff: data.staff,
                  published: published,
                  onAssign: () => _assign(context, rec['station'] as String, data, reload),
                  onAttendance: (a, status) => _setAttendance(context, a, status, reload),
                ),
                const SizedBox(height: 16),
              ],
              if (!published)
                FilledButton.icon(
                  onPressed: () => _publish(context, data, reload),
                  icon: const Icon(Icons.publish_rounded),
                  label: const Text('Publish schedule'),
                )
              else if (data.closingReport == null)
                FilledButton.icon(
                  onPressed: () => _closeShift(context, reload),
                  icon: const Icon(Icons.flag_rounded),
                  label: const Text('Close shift and report'),
                )
              else
                _ClosingCard(report: data.closingReport!),
            ],
          );
        },
      ),
    );
  }
}

class _StationSection extends StatelessWidget {
  final Json recommendation;
  final List<Json> assignments;
  final Map<int, Json> staff;
  final bool published;
  final VoidCallback onAssign;
  final void Function(Json assignment, String status) onAttendance;

  const _StationSection({
    required this.recommendation,
    required this.assignments,
    required this.staff,
    required this.published,
    required this.onAssign,
    required this.onAttendance,
  });

  @override
  Widget build(BuildContext context) {
    final recommended = recommendation['recommended_staff_count'] as int;
    final assigned = assignments.length;
    final short = recommended - assigned;
    final scheme = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                recommendation['station'] as String,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            Text('Recommended: $recommended', style: TextStyle(color: scheme.onSurfaceVariant)),
          ],
        ),
        const SizedBox(height: 4),
        // The flag appears as staff are assigned, before publishing.
        if (!published)
          SeverityChip(
            label: short > 0
                ? '$short below recommendation ($assigned of $recommended)'
                : short == 0
                    ? 'Meets recommendation ($assigned of $recommended)'
                    : '${-short} above recommendation ($assigned of $recommended)',
            color: short > 0 ? Severity.warning : Severity.ok,
          ),
        const SizedBox(height: 8),
        for (final a in assignments)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Card(
              child: ListTile(
                leading: const IconBadge(icon: Icons.person_rounded),
                title: Text(staff[a['staff_id']]?['name'] as String? ?? 'Staff #${a['staff_id']}'),
                subtitle: Text(staff[a['staff_id']]?['role'] as String? ?? ''),
                trailing: published ? _AttendanceControl(assignment: a, onChange: onAttendance) : null,
              ),
            ),
          ),
        if (!published) AddRow(label: 'Assign staff', onTap: onAssign),
      ],
    );
  }
}

class _AttendanceControl extends StatelessWidget {
  final Json assignment;
  final void Function(Json assignment, String status) onChange;

  const _AttendanceControl({required this.assignment, required this.onChange});

  @override
  Widget build(BuildContext context) {
    final status = assignment['attendance_status'] as String;
    return SegmentedButton<String>(
      showSelectedIcon: false,
      segments: const [
        ButtonSegment(value: 'confirmed', label: Text('Here')),
        ButtonSegment(value: 'absent', label: Text('Absent')),
      ],
      emptySelectionAllowed: true,
      selected: status == 'confirmed' || status == 'absent' ? {status} : <String>{},
      onSelectionChanged: (selection) {
        if (selection.isNotEmpty) onChange(assignment, selection.first);
      },
    );
  }
}

class _ClosingCard extends StatelessWidget {
  final Json report;

  const _ClosingCard({required this.report});

  @override
  Widget build(BuildContext context) {
    final forecast = report['forecasted_volume'];
    final variance = report['variance'] as int?;
    final scheme = Theme.of(context).colorScheme;
    final color = variance == null ? scheme.outline : (variance.abs() <= 10 ? Severity.ok : Severity.warning);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionHeader(icon: Icons.flag_rounded, label: 'Shift closed'),
            Text('Actual: ${report['actual_order_volume']} portions',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            if (forecast == null)
              const Text('No forecast was available for this shift to compare against.')
            else
              Row(
                children: [
                  Expanded(child: Text('Forecast: $forecast portions')),
                  SeverityChip(
                    label: variance == 0
                        ? 'On forecast'
                        : '${variance! > 0 ? '+' : ''}$variance vs forecast',
                    color: color,
                  ),
                ],
              ),
            if ((report['notes'] as String?)?.isNotEmpty ?? false) ...[
              const SizedBox(height: 8),
              Text(report['notes'] as String),
            ],
          ],
        ),
      ),
    );
  }
}
