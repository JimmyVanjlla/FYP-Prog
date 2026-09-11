import 'package:flutter/material.dart';

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

/// App-wide theme. Kept deliberately plain (no custom fonts) so it matches
/// what the generated PDF reports can also reproduce with ReportLab's base
/// fonts (Ch4 §4.7.2).
ThemeData buildAppTheme() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1565C0)),
  );
  return base.copyWith(
    appBarTheme: base.appBarTheme.copyWith(centerTitle: false),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      ),
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

/// A small severity chip: color + text together, never color alone.
class SeverityChip extends StatelessWidget {
  final String label;
  final Color color;

  const SeverityChip({super.key, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontWeight: FontWeight.w600,
          fontSize: 12,
        ),
      ),
    );
  }
}
