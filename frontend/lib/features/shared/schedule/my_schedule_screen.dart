import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/async_view.dart';
import '../../../core/auth_state.dart';
import '../../../core/format.dart';
import '../../../core/json.dart';
import '../../../core/theme.dart';

/// UC-SS-05 — any staff member's own published shifts, without needing to
/// know a schedule id or go through the Shift Supervisor.
class MyScheduleScreen extends StatelessWidget {
  const MyScheduleScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final api = context.read<AuthState>().api;
    return AsyncView<List<Json>>(
      load: () async => asJsonList(await api.getJson('/staffing/my-schedule')),
      builder: (context, shifts, reload) {
        final today = fmtDate(DateTime.now());
        final upcoming = shifts.where((s) => (s['date'] as String).compareTo(today) >= 0).toList();
        final past = shifts.where((s) => (s['date'] as String).compareTo(today) < 0).toList();
        return RefreshableList(
          onRefresh: reload,
          empty: const EmptyState(
            icon: Icons.event_busy_rounded,
            message: 'No shifts assigned to you yet.',
            detail: 'Published shifts will show up here.',
          ),
          children: [
            if (upcoming.isNotEmpty) const SectionHeader(icon: Icons.event_rounded, label: 'Upcoming'),
            for (final s in upcoming) _ShiftTile(shift: s),
            if (past.isNotEmpty) ...[
              const SizedBox(height: 14),
              const SectionHeader(icon: Icons.history_rounded, label: 'Past'),
              for (final s in past.reversed.take(20)) _ShiftTile(shift: s),
            ],
          ],
        );
      },
    );
  }
}

class _ShiftTile extends StatelessWidget {
  final Json shift;

  const _ShiftTile({required this.shift});

  @override
  Widget build(BuildContext context) {
    final attendance = shift['attendance_status'] as String;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Card(
        child: ListTile(
          leading: const IconBadge(icon: Icons.schedule_rounded),
          title: Text('${friendlyDate(shift['date'])}  ·  ${shift['meal_period']}'),
          subtitle: Text('Station: ${shift['station']}'),
          trailing: SeverityChip(
            label: attendance == 'confirmed' ? 'Confirmed' : (attendance == 'absent' ? 'Absent' : 'Scheduled'),
            color: attendance == 'confirmed'
                ? Severity.ok
                : (attendance == 'absent' ? Severity.critical : Severity.warning),
          ),
        ),
      ),
    );
  }
}
