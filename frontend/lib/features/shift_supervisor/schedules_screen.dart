import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/async_view.dart';
import '../../core/auth_state.dart';
import '../../core/dialogs.dart';
import '../../core/format.dart';
import '../../core/json.dart';
import '../../core/theme.dart';
import 'schedule_builder_screen.dart';

/// FR8.2 — the Shift Supervisor's shift schedules, newest first, and a way to
/// start a new one. Each opens the Schedule Builder.
class SchedulesScreen extends StatefulWidget {
  const SchedulesScreen({super.key});

  @override
  State<SchedulesScreen> createState() => _SchedulesScreenState();
}

class _SchedulesScreenState extends State<SchedulesScreen> {
  int _version = 0;

  Future<void> _open(Json schedule) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ScheduleBuilderScreen(schedule: schedule)),
    );
    if (mounted) setState(() => _version++);
  }

  Future<void> _create(BuildContext context) async {
    DateTime date = DateTime.now();
    String period = 'Lunch';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('New shift schedule'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Date'),
                subtitle: Text(friendlyDate(fmtDate(date))),
                trailing: const Icon(Icons.calendar_today_rounded),
                onTap: () async {
                  final d = await pickDate(context, initial: date, first: DateTime.now().subtract(const Duration(days: 1)));
                  if (d != null) setState(() => date = d);
                },
              ),
              DropdownButtonFormField<String>(
                initialValue: period,
                decoration: const InputDecoration(labelText: 'Meal period'),
                items: mealPeriods.map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
                onChanged: (v) => setState(() => period = v ?? period),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Create')),
          ],
        ),
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final api = context.read<AuthState>().api;
    Json? created;
    final ok = await runAction(context, () async {
      created = asJson(
        await api.postJson('/staffing/schedules', {'date': fmtDate(date), 'meal_period': period}),
      );
    });
    if (ok && created != null && mounted) await _open(created!);
  }

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<List<Json>>(
      key: ValueKey(_version),
      load: () async => asJsonList(await api.getJson('/staffing/schedules', query: {'limit': 200})),
      builder: (context, schedules, reload) => RefreshableList(
        onRefresh: reload,
        children: [
          AddRow(label: 'New shift schedule', onTap: () => _create(context)),
          const SizedBox(height: 14),
          for (final s in schedules) ...[
            Card(
              child: ListTile(
                onTap: () => _open(s),
                leading: const IconBadge(icon: Icons.event_note_rounded),
                title: Text('${friendlyDate(s['date'])}  ·  ${s['meal_period']}'),
                subtitle: Text(s['status'] == 'published' ? 'Published' : 'Draft, not yet published'),
                trailing: SeverityChip(
                  label: s['status'] == 'published' ? 'Published' : 'Draft',
                  color: s['status'] == 'published' ? Severity.ok : Severity.warning,
                ),
              ),
            ),
            const SizedBox(height: 10),
          ],
          if (schedules.isEmpty)
            const EmptyState(
              icon: Icons.event_busy_rounded,
              message: 'No shift schedules yet.',
              detail: 'Create one to see the recommended staffing and build the roster.',
            ),
        ],
      ),
    );
  }
}
