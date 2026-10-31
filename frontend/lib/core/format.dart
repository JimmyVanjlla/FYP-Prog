// Date helpers shared by the screens (ISO yyyy-MM-dd, the format the API
// speaks in both directions).

String fmtDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

DateTime? parseDate(dynamic value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString());
}

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/// "Fri 31 Oct"
String friendlyDate(dynamic value) {
  final d = parseDate(value);
  if (d == null) return '';
  return '${_weekdays[d.weekday - 1]} ${d.day} ${_months[d.month - 1]}';
}

/// "31 Oct" (no weekday) for tight spaces.
String shortDate(dynamic value) {
  final d = parseDate(value);
  if (d == null) return '';
  return '${d.day} ${_months[d.month - 1]}';
}

/// "31 Oct, 14:05" for a timestamp.
String friendlyDateTime(dynamic value) {
  final d = parseDate(value)?.toLocal();
  if (d == null) return '';
  final hh = d.hour.toString().padLeft(2, '0');
  final mm = d.minute.toString().padLeft(2, '0');
  return '${d.day} ${_months[d.month - 1]}, $hh:$mm';
}

const mealPeriods = ['Breakfast', 'Lunch', 'Dinner'];
