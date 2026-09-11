/// Mirrors the backend's ReportOut schema (app/schemas/reporting.py).
class Report {
  final int reportId;
  final String type;
  final String periodStart;
  final String periodEnd;
  final String status;
  final bool hasPdf;

  Report({
    required this.reportId,
    required this.type,
    required this.periodStart,
    required this.periodEnd,
    required this.status,
    required this.hasPdf,
  });

  factory Report.fromJson(Map<String, dynamic> json) {
    return Report(
      reportId: json['report_id'] as int,
      type: json['type'] as String,
      periodStart: json['period_start'] as String,
      periodEnd: json['period_end'] as String,
      status: json['status'] as String,
      hasPdf: json['pdf_path'] != null,
    );
  }
}
