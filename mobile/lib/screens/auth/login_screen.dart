import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:toastification/toastification.dart';
import '../../providers/auth_provider.dart';
import '../../theme.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});
  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _obscurePass = true;
  bool _loading = false;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    try {
      await ref.read(authProvider.notifier).login(_emailCtrl.text.trim(), _passCtrl.text);
    } catch (e) {
      if (mounted) {
        toastification.show(
          context: context,
          title: const Text('Anmeldung fehlgeschlagen'),
          description: Text(e.toString()),
          type: ToastificationType.error,
          autoCloseDuration: const Duration(seconds: 4),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.surface,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 48),
              // EU Star logo
              Center(
                child: Container(
                  width: 80, height: 80,
                  decoration: const BoxDecoration(
                    color: AppTheme.primary,
                    shape: BoxShape.circle,
                  ),
                  child: const Center(
                    child: Text('⭐', style: TextStyle(fontSize: 36)),
                  ),
                ).animate().scale(duration: 400.ms),
              ),
              const SizedBox(height: 24),
              Center(
                child: Text(
                  'EU-Bagatellverfahren',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                    color: AppTheme.primary,
                  ),
                ).animate().fadeIn(delay: 200.ms),
              ),
              Center(
                child: Text(
                  'Anmelden',
                  style: TextStyle(fontSize: 14, color: Colors.grey.shade600),
                ).animate().fadeIn(delay: 300.ms),
              ),
              const SizedBox(height: 40),
              Form(
                key: _formKey,
                child: Column(children: [
                  TextFormField(
                    controller: _emailCtrl,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'E-Mail',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    validator: (v) => v != null && v.contains('@') ? null : 'Ungültige E-Mail',
                  ).animate().fadeIn(delay: 350.ms).slideX(begin: -0.05),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _passCtrl,
                    obscureText: _obscurePass,
                    textInputAction: TextInputAction.done,
                    onFieldSubmitted: (_) => _login(),
                    decoration: InputDecoration(
                      labelText: 'Passwort',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(_obscurePass ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                        onPressed: () => setState(() => _obscurePass = !_obscurePass),
                      ),
                    ),
                    validator: (v) => v != null && v.length >= 6 ? null : 'Mindestens 6 Zeichen',
                  ).animate().fadeIn(delay: 400.ms).slideX(begin: -0.05),
                  const SizedBox(height: 28),
                  FilledButton(
                    onPressed: _loading ? null : _login,
                    child: _loading
                        ? const SizedBox(
                            width: 20, height: 20,
                            child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                          )
                        : const Text('Anmelden'),
                  ).animate().fadeIn(delay: 450.ms),
                  const SizedBox(height: 16),
                  OutlinedButton(
                    onPressed: () => context.go('/auth/register'),
                    child: const Text('Konto erstellen'),
                  ).animate().fadeIn(delay: 500.ms),
                  const SizedBox(height: 20),
                  // Demo hint
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppTheme.primary.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppTheme.primary.withOpacity(0.2)),
                    ),
                    child: const Row(children: [
                      Icon(Icons.info_outline, size: 16, color: AppTheme.primary),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Demo: admin@portal.eu / admin1234',
                          style: TextStyle(fontSize: 12, color: AppTheme.primary),
                        ),
                      ),
                    ]),
                  ).animate().fadeIn(delay: 550.ms),
                ]),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
