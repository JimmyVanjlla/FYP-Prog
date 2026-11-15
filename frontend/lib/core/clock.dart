/// The restaurant's clock. The app is for a restaurant in Malaysia (UTC+8), so
/// "today" means today there, whatever the phone's own timezone is set to (an
/// emulator or a phone left on UTC would otherwise be a day behind for the
/// first eight hours of every Malaysian day).
const restaurantUtcOffset = Duration(hours: 8);

/// The current date and time on the restaurant's wall clock.
DateTime restaurantNow({DateTime? now}) {
  final n = (now ?? DateTime.now()).toUtc().add(restaurantUtcOffset);
  return DateTime(n.year, n.month, n.day, n.hour, n.minute, n.second);
}

/// Today's date (midnight) at the restaurant.
DateTime restaurantToday({DateTime? now}) {
  final n = restaurantNow(now: now);
  return DateTime(n.year, n.month, n.day);
}
