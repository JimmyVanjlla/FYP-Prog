import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth_state.dart';
import 'kitchen_staff/leftover_log_screen.dart';
import 'kitchen_staff/prep_screen.dart';
import 'manager/approvals_screen.dart';
import 'manager/reports_screen.dart';
import 'manager/settings_screen.dart';
import 'manager/staff_screen.dart';
import 'manager/waste_screen.dart';
import 'procurement_officer/purchase_orders_screen.dart';
import 'procurement_officer/suppliers_screen.dart';
import 'shared/deliveries/deliveries_screen.dart';
import 'shared/forecasts/forecast_dashboard_screen.dart';
import 'shared/inventory/inventory_list_screen.dart';
import 'shared/inventory/restocking_requests_screen.dart';
import 'shared/menu/menu_list_screen.dart';
import 'shared/notifications/notifications_screen.dart';
import 'shared/schedule/my_schedule_screen.dart';
import 'shift_supervisor/schedules_screen.dart';

/// A place a role can go: a label, an icon, and the screen.
class Destination {
  final String label;
  final IconData icon;
  final Widget screen;

  const Destination(this.label, this.icon, this.screen);
}

const _menu = Destination('Menu', Icons.restaurant_menu_rounded, MenuListScreen());
const _inventory = Destination('Inventory', Icons.inventory_2_rounded, InventoryListScreen());
const _forecasts = Destination('Forecasts', Icons.insights_rounded, ForecastDashboardScreen());
const _deliveries = Destination('Deliveries', Icons.local_shipping_rounded, DeliveriesScreen());
const _myShifts = Destination('My shifts', Icons.schedule_rounded, MyScheduleScreen());

/// Ch4 section 4.4.1 / FR1.3 / NFR-Usability: "presenting each role with
/// only the screens and functions relevant to their responsibilities". The
/// server enforces the same boundaries independently; this just means a
/// role is never shown something it would get a 403 for.
List<Destination> destinationsFor(String? role) {
  switch (role) {
    case Roles.manager:
      return const [
        Destination('Needs attention', Icons.fact_check_rounded, ApprovalsScreen()),
        _menu,
        _inventory,
        _forecasts,
        Destination('Waste', Icons.delete_outline_rounded, WasteScreen()),
        Destination('Reports', Icons.summarize_rounded, ReportsScreen()),
        Destination('Purchasing', Icons.receipt_long_rounded, PurchaseOrdersScreen()),
        _deliveries,
        Destination('Staff', Icons.groups_rounded, StaffScreen()),
        Destination('Settings', Icons.tune_rounded, SettingsScreen()),
      ];
    case Roles.owner:
      return const [
        _forecasts,
        Destination('Waste', Icons.delete_outline_rounded, WasteScreen()),
        _menu,
        _inventory,
        _deliveries,
      ];
    case Roles.kitchenStaff:
      return const [
        Destination('Prep', Icons.soup_kitchen_rounded, PrepScreen()),
        Destination('Leftovers', Icons.restaurant_rounded, LeftoverLogScreen()),
        _menu,
        _inventory,
        _myShifts,
      ];
    case Roles.inventoryStaff:
      return const [
        _inventory,
        Destination('Restock requests', Icons.add_shopping_cart_rounded, RestockingRequestsScreen()),
        _deliveries,
        _menu,
        _myShifts,
      ];
    case Roles.shiftSupervisor:
      return const [
        Destination('Schedules', Icons.event_note_rounded, SchedulesScreen()),
        _forecasts,
        _menu,
        _myShifts,
      ];
    case Roles.procurementOfficer:
      return const [
        Destination('Purchasing', Icons.receipt_long_rounded, PurchaseOrdersScreen()),
        Destination('Suppliers', Icons.storefront_rounded, SuppliersScreen()),
        _deliveries,
        _menu,
        _myShifts,
      ];
    case Roles.deliveryStaff:
      return const [_deliveries, _myShifts];
    default:
      return const [_menu];
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final destinations = destinationsFor(auth.role);
    final index = _index < destinations.length ? _index : 0;
    final current = destinations[index];
    // A bottom bar holds five comfortably; a role with more gets a drawer.
    final useDrawer = destinations.length > 5;

    return Scaffold(
      appBar: AppBar(
        title: Text(current.label),
        actions: [
          IconButton(
            tooltip: 'Notifications',
            icon: const Icon(Icons.notifications_none_rounded),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => Scaffold(
                  appBar: AppBar(title: const Text('Notifications')),
                  body: const NotificationsScreen(),
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Log out',
            icon: const Icon(Icons.logout),
            onPressed: () => context.read<AuthState>().logout(),
          ),
        ],
      ),
      drawer: useDrawer
          ? NavigationDrawer(
              selectedIndex: index,
              onDestinationSelected: (i) {
                setState(() => _index = i);
                Navigator.of(context).pop();
              },
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(28, 24, 16, 12),
                  child: Text(
                    auth.role ?? '',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                for (final d in destinations)
                  NavigationDrawerDestination(icon: Icon(d.icon), label: Text(d.label)),
              ],
            )
          : null,
      body: current.screen,
      bottomNavigationBar: !useDrawer && destinations.length > 1
          ? NavigationBar(
              selectedIndex: index,
              onDestinationSelected: (i) => setState(() => _index = i),
              destinations: [
                for (final d in destinations) NavigationDestination(icon: Icon(d.icon), label: d.label),
              ],
            )
          : null,
    );
  }
}
