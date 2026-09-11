import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/auth_state.dart';
import 'core/theme.dart';
import 'features/auth/login_screen.dart';
import 'features/menu/menu_list_screen.dart';

void main() {
  runApp(const RestaurantOpsApp());
}

class RestaurantOpsApp extends StatelessWidget {
  const RestaurantOpsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AuthState()..restoreSession(),
      child: MaterialApp(
        title: 'Restaurant Ops',
        debugShowCheckedModeBanner: false,
        theme: buildAppTheme(),
        home: const _RootRouter(),
      ),
    );
  }
}

/// Routes to the login screen or the (role-appropriate, in later sprints)
/// authenticated shell based on AuthState — no role selector anywhere here,
/// role is decoded from the JWT (Ch4 §4.4.1).
class _RootRouter extends StatelessWidget {
  const _RootRouter();

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    if (auth.isRestoring) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return auth.isAuthenticated ? const MenuListScreen() : const LoginScreen();
  }
}
