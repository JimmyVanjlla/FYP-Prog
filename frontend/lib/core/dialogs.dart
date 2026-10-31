import 'package:flutter/material.dart';

/// Asks for a single number, validating it inline as it's typed (Ch4
/// section 4.4.1: exceptions surface at the point of entry, not after
/// submission). Returns the entered text, or null if cancelled.
///
/// [check] returns an error message for an invalid value, or null if fine.
Future<String?> promptNumber(
  BuildContext context, {
  required String title,
  required String label,
  String? helper,
  String? initial,
  String? suffix,
  String confirmLabel = 'Save',
  String? Function(double value)? check,
  bool allowEmpty = false,
  String? emptyHelper,
}) {
  final controller = TextEditingController(text: initial ?? '');
  final formKey = GlobalKey<FormState>();
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Form(
        key: formKey,
        child: TextFormField(
          controller: controller,
          autofocus: true,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
          decoration: InputDecoration(
            labelText: label,
            helperText: allowEmpty ? (emptyHelper ?? helper) : helper,
            suffixText: suffix,
          ),
          validator: (v) {
            final text = v?.trim() ?? '';
            if (text.isEmpty) return allowEmpty ? null : 'Enter a number.';
            final value = double.tryParse(text);
            if (value == null) return 'Enter a number.';
            return check?.call(value);
          },
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            if (formKey.currentState!.validate()) Navigator.pop(context, controller.text.trim());
          },
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
}

/// Asks for a free-text answer (e.g. a reason). Returns null if cancelled.
Future<String?> promptText(
  BuildContext context, {
  required String title,
  required String label,
  String confirmLabel = 'Save',
  bool required = true,
  int maxLines = 3,
}) {
  final controller = TextEditingController();
  final formKey = GlobalKey<FormState>();
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Form(
        key: formKey,
        child: TextFormField(
          controller: controller,
          autofocus: true,
          maxLines: maxLines,
          decoration: InputDecoration(labelText: label),
          validator: (v) => required && (v == null || v.trim().isEmpty) ? 'Required.' : null,
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            if (formKey.currentState!.validate()) Navigator.pop(context, controller.text.trim());
          },
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
}

/// Yes/no confirmation for something consequential.
Future<bool> confirmAction(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(confirmLabel)),
      ],
    ),
  );
  return result == true;
}

/// A date field that opens the date picker.
Future<DateTime?> pickDate(BuildContext context, {DateTime? initial, DateTime? first, DateTime? last}) {
  return showDatePicker(
    context: context,
    initialDate: initial ?? DateTime.now(),
    firstDate: first ?? DateTime(2020),
    lastDate: last ?? DateTime(2100),
  );
}
