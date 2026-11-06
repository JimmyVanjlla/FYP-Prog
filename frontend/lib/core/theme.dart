import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// The system's single fixed 3-state severity palette (Ch4 §4.4.1: "Severity
/// is color plus text, from one fixed palette"). Every screen that flags low
/// stock, an over-budget order, a delivery mismatch, etc. reuses these three
/// colors rather than inventing its own — and severity is always paired with
/// a text label, never conveyed by color alone.
class Severity {
  static const Color critical = Color(
    0xFFD32F2F,
  ); // e.g. below low-stock threshold
  static const Color warning = Color(
    0xFFED8F00,
  ); // e.g. approaching a threshold
  static const Color ok = Color(0xFF2E7D32); // e.g. on track / within range

  const Severity._();
}

/// The brand colour: a vivid indigo. It is deliberately nowhere near the
/// severity palette above (red, amber, green), so a status colour is never
/// confused with decoration.
const Color brandColor = Color(0xFF3949DB);

/// The page behind the cards: a light cool tint, so white cards stand out
/// from it instead of grey cards sitting on near-white.
const Color pageBackground = Color(0xFFF2F4FB);

/// App-wide theme. No custom font family — this is deliberate, so the app's
/// typography stays reproducible by the generated PDF reports' ReportLab
/// base fonts (Ch4 §4.7.2). Visual richness instead comes from a vivid
/// Material 3 colour scheme, white cards with soft shadows, a coloured top
/// bar, gradient banners and consistent rounding/spacing, not from typography.
ThemeData buildAppTheme() {
  final colorScheme = ColorScheme.fromSeed(
    seedColor: brandColor,
    dynamicSchemeVariant: DynamicSchemeVariant.vibrant,
  );
  final base = ThemeData(useMaterial3: true, colorScheme: colorScheme);
  final outline = colorScheme.outlineVariant.withValues(alpha: 0.7);

  return base.copyWith(
    scaffoldBackgroundColor: pageBackground,
    textTheme: base.textTheme.copyWith(
      headlineMedium: base.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800),
      headlineSmall: base.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
      titleLarge: base.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
      titleMedium: base.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
      titleSmall: base.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
    ),
    appBarTheme: AppBarTheme(
      centerTitle: false,
      elevation: 0,
      scrolledUnderElevation: 0,
      backgroundColor: colorScheme.primary,
      foregroundColor: colorScheme.onPrimary,
      iconTheme: IconThemeData(color: colorScheme.onPrimary),
      actionsIconTheme: IconThemeData(color: colorScheme.onPrimary),
      systemOverlayStyle: SystemUiOverlayStyle.light,
      titleTextStyle: base.textTheme.titleLarge?.copyWith(
        fontWeight: FontWeight.w800,
        color: colorScheme.onPrimary,
      ),
    ),
    tabBarTheme: TabBarThemeData(
      labelColor: colorScheme.primary,
      unselectedLabelColor: colorScheme.onSurfaceVariant,
      indicatorColor: colorScheme.primary,
      indicatorSize: TabBarIndicatorSize.tab,
      dividerColor: outline,
      labelStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
      unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
    ),
    navigationDrawerTheme: NavigationDrawerThemeData(
      backgroundColor: Colors.white,
      indicatorColor: colorScheme.primaryContainer,
      surfaceTintColor: Colors.transparent,
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 68,
      backgroundColor: Colors.white,
      indicatorColor: colorScheme.primaryContainer,
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        final selected = states.contains(WidgetState.selected);
        return TextStyle(
          fontSize: 12,
          fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
          color: selected ? colorScheme.onSurface : colorScheme.onSurfaceVariant,
        );
      }),
    ),
    cardTheme: CardThemeData(
      elevation: 1.5,
      shadowColor: colorScheme.primary.withValues(alpha: 0.18),
      margin: EdgeInsets.zero,
      color: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: outline),
      ),
    ),
    listTileTheme: ListTileThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      iconColor: colorScheme.primary,
      titleTextStyle: base.textTheme.titleMedium?.copyWith(
        fontWeight: FontWeight.w700,
        color: colorScheme.onSurface,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: colorScheme.primary, width: 1.8),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: colorScheme.error, width: 1.2),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: colorScheme.error, width: 1.8),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        side: BorderSide(color: colorScheme.primary.withValues(alpha: 0.5)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: Colors.white,
      selectedColor: colorScheme.primaryContainer,
      side: BorderSide(color: outline),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    ),
    dividerTheme: DividerThemeData(color: outline, thickness: 1, space: 32),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
  );
}

/// One recurring interaction pattern (Ch4 §4.4.1: "One interaction pattern,
/// reused everywhere it recurs") — filled-primary paired with
/// outlined-secondary for every approve/reject or confirm/cancel action.
class PrimarySecondaryActions extends StatelessWidget {
  final String primaryLabel;
  final String secondaryLabel;
  final VoidCallback onPrimary;
  final VoidCallback onSecondary;

  const PrimarySecondaryActions({
    super.key,
    required this.primaryLabel,
    required this.secondaryLabel,
    required this.onPrimary,
    required this.onSecondary,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton(
            onPressed: onSecondary,
            child: Text(secondaryLabel),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: FilledButton(onPressed: onPrimary, child: Text(primaryLabel)),
        ),
      ],
    );
  }
}

/// A small severity chip: color + text together, never color alone. The
/// leading icon is derived from which of the 3 fixed severity colors was
/// passed in, so every call site gets it automatically without having to
/// name an icon itself.
class SeverityChip extends StatelessWidget {
  final String label;
  final Color color;

  const SeverityChip({super.key, required this.label, required this.color});

  IconData get _icon {
    if (color == Severity.critical) return Icons.error_rounded;
    if (color == Severity.warning) return Icons.warning_rounded;
    if (color == Severity.ok) return Icons.check_circle_rounded;
    return Icons.circle;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_icon, color: color, size: 13),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w700,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A consistent "nothing here yet" state — icon, message, optional
/// secondary line — used instead of a bare line of text so every screen's
/// empty state looks like a deliberate state, not a missing one.
class EmptyState extends StatelessWidget {
  final IconData icon;
  final String message;
  final String? detail;

  const EmptyState({super.key, required this.icon, required this.message, this.detail});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 40, color: scheme.onSurfaceVariant.withValues(alpha: 0.6)),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                color: scheme.onSurfaceVariant,
                fontWeight: FontWeight.w600,
              ),
            ),
            if (detail != null) ...[
              const SizedBox(height: 4),
              Text(
                detail!,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: scheme.onSurfaceVariant.withValues(alpha: 0.8),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A small icon + label row used above a grouped list (e.g. "Pending
/// purchase orders"), reused wherever a screen needs more than one section.
class SectionHeader extends StatelessWidget {
  final IconData icon;
  final String label;
  final String? trailing;

  /// Tints the icon, for a group that stands for a status (for example the
  /// critical colour above a list of low-stock items). Defaults to the brand colour.
  final Color? color;

  const SectionHeader({super.key, required this.icon, required this.label, this.trailing, this.color});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Icon(icon, size: 18, color: color ?? scheme.primary),
          const SizedBox(width: 8),
          Expanded(
            child: Text(label, style: Theme.of(context).textTheme.titleMedium),
          ),
          if (trailing != null)
            Text(
              trailing!,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
            ),
        ],
      ),
    );
  }
}

/// A tinted rounded-square icon badge used as a list tile's leading widget, so
/// every list (menu, inventory, reports…) gets the same look instead of a
/// bare icon or nothing at all.
class IconBadge extends StatelessWidget {
  final IconData icon;
  final Color? color;

  const IconBadge({super.key, required this.icon, this.color});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final tint = color ?? scheme.primary;
    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: tint.withValues(alpha: 0.13),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Icon(icon, color: tint, size: 22),
    );
  }
}

/// The brand gradient, used for the banner at the top of a screen and the
/// drawer and login headers.
LinearGradient brandGradient(BuildContext context) {
  final scheme = Theme.of(context).colorScheme;
  return LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [scheme.primary, Color.lerp(scheme.primary, scheme.tertiary, 0.6)!],
  );
}

/// A banner at the top of a screen: what this screen is about, in one line,
/// with the headline number big. Always readable (white on the gradient).
class HeroBanner extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;

  /// A big figure on the right, such as how many items need attention.
  final String? figure;

  const HeroBanner({super.key, required this.icon, required this.title, required this.subtitle, this.figure});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: brandGradient(context),
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
            color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.28),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(icon, color: Colors.white, size: 26),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 2),
                Text(subtitle, style: TextStyle(color: Colors.white.withValues(alpha: 0.9), fontSize: 13)),
              ],
            ),
          ),
          if (figure != null) ...[
            const SizedBox(width: 12),
            Text(figure!, style: const TextStyle(color: Colors.white, fontSize: 34, fontWeight: FontWeight.w800)),
          ],
        ],
      ),
    );
  }
}

/// One number with a label, in a tinted tile. When the number is a status
/// (for example low stock), pass the severity colour: the label still says
/// what it is, so the colour is never the only signal.
class StatTile extends StatelessWidget {
  final IconData icon;
  final String value;
  final String label;
  final Color? color;

  const StatTile({super.key, required this.icon, required this.value, required this.label, this.color});

  @override
  Widget build(BuildContext context) {
    final tint = color ?? Theme.of(context).colorScheme.primary;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: tint.withValues(alpha: 0.09),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: tint.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: tint, size: 22),
          const SizedBox(height: 10),
          Text(value, style: TextStyle(color: tint, fontSize: 26, fontWeight: FontWeight.w800, height: 1)),
          const SizedBox(height: 4),
          Text(
            label,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}


/// The dashed "+ add" row Chapter 4 (section 4.4.1) names as the one
/// interaction pattern for adding something to a list — "the same pattern
/// as '+ Assign staff' on Schedule Builder; same pattern for every status
/// list". One widget so every screen's add row looks and behaves the same.
class AddRow extends StatelessWidget {
  final String label;
  final VoidCallback onTap;

  const AddRow({super.key, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          border: Border.all(color: primary.withValues(alpha: 0.4)),
          borderRadius: BorderRadius.circular(16),
        ),
        alignment: Alignment.center,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.add_rounded, size: 18, color: primary),
            const SizedBox(width: 6),
            Text(label, style: TextStyle(color: primary, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}
