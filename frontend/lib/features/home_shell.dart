import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth_state.dart';
import 'inventory/inventory_list_screen.dart';
import 'kitchen/leftover_log_screen.dart';
import 'manager/approvals_screen.dart';
import 'manager/reports_screen.dart';
import 'manager/waste_screen.dart';
import 'menu/menu_list_screen.dart';

/// Role-scoped bottom navigation — each tab is a module screen; a role only
/// sees tabs relevant to it (Ch4 §4.4.1: "presenting each role with only
/// the screens and functions relevant to their responsibilities").
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final role = context.watch<AuthState>().role;
    final tabs = _tabsForRole(role);
    final safeIndex = _index < tabs.length ? _index : 0;

    return Scaffold(
      appBar: AppBar(
        title: Text(tabs[safeIndex].label),
        actions: [
          IconButton(
            tooltip: 'Log out',
            icon: const Icon(Icons.logout),
            onPressed: () => context.read<AuthState>().logout(),
          ),
        ],
      ),
      body: tabs[safeIndex].screen,
      bottomNavigationBar: tabs.length > 1
          ? NavigationBar(
              selectedIndex: safeIndex,
              onDestinationSelected: (i) => setState(() => _index = i),
              destinations: tabs
                  .map(
                    (t) => NavigationDestination(
                      icon: Icon(t.icon),
                      label: t.label,
                    ),
                  )
                  .toList(),
            )
          : null,
    );
  }

  List<_Tab> _tabsForRole(String? role) {
    final tabs = <_Tab>[
      const _Tab('Menu', Icons.restaurant_menu, MenuListScreen()),
    ];
    if (role == Roles.inventoryStaff ||
        role == Roles.manager ||
        role == Roles.kitchenStaff) {
      tabs.add(
        const _Tab('Inventory', Icons.inventory_2, InventoryListScreen()),
      );
    }
    if (role == Roles.kitchenStaff) {
      tabs.add(const _Tab('Leftovers', Icons.restaurant, LeftoverLogScreen()));
    }
    if (role == Roles.manager) {
      tabs.add(const _Tab('Approvals', Icons.fact_check, ApprovalsScreen()));
      tabs.add(const _Tab('Waste', Icons.delete_outline, WasteScreen()));
      tabs.add(const _Tab('Reports', Icons.summarize, ReportsScreen()));
    }
    return tabs;
  }
}

class _Tab {
  final String label;
  final IconData icon;
  final Widget screen;

  const _Tab(this.label, this.icon, this.screen);
}
