import 'package:flutter/material.dart';

/// The meal periods a dish can be served in, in day order.
const mealPeriodOptions = ['Breakfast', 'Lunch', 'Dinner'];

/// Which meal periods a dish is served in. Prep, forecasts and leftovers only
/// consider a dish in the periods chosen here; at least one must stay chosen.
class MealPeriodPicker extends StatelessWidget {
  final Set<String> selected;
  final ValueChanged<Set<String>> onChanged;

  const MealPeriodPicker({super.key, required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Served at', style: Theme.of(context).textTheme.labelLarge),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: [
            for (final period in mealPeriodOptions)
              FilterChip(
                label: Text(period),
                selected: selected.contains(period),
                onSelected: (on) {
                  final next = {...selected};
                  if (on) {
                    next.add(period);
                  } else if (next.length > 1) {
                    next.remove(period); // a dish is always served at something
                  }
                  onChanged(next);
                },
              ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'Prep and forecasts only include this dish in these meal periods.',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
        ),
      ],
    );
  }
}
