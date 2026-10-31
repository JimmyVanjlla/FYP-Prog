import 'package:flutter/material.dart';

import 'theme.dart';

/// How a purchase order / delivery status is shown: a plain-language label
/// plus one of the three fixed severity colours (Ch4 section 4.4.1). The PO
/// and the delivery share one lifecycle once an order is approved (UC-DM-04,
/// UC-PS-05), so they share one mapping.
typedef StatusStyle = ({String label, Color color});

StatusStyle statusStyle(String status) {
  switch (status) {
    case 'pending_approval':
      return (label: 'Awaiting approval', color: Severity.warning);
    case 'approved':
      return (label: 'Approved', color: Severity.ok);
    case 'rejected':
      return (label: 'Rejected', color: Severity.critical);
    case 'awaiting_delivery':
      return (label: 'Awaiting delivery', color: Severity.warning);
    case 'in_transit':
      return (label: 'In transit', color: Severity.warning);
    case 'delivered':
      return (label: 'Received', color: Severity.ok);
    case 'discrepancy_flagged':
      return (label: 'Discrepancy', color: Severity.critical);
    case 'return_pending':
      return (label: 'Return pending', color: Severity.critical);
    case 'return_resolved':
      return (label: 'Resolved', color: Severity.ok);
    default:
      return (label: status, color: Severity.warning);
  }
}
