import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/case.dart';
import '../models/chat_message.dart';
import '../models/process_score.dart';
import '../services/case_service.dart';

// ── Cases list ──────────────────────────────────────────────────────────────

class CasesNotifier extends AsyncNotifier<List<Case>> {
  final _svc = CaseService();

  @override
  Future<List<Case>> build() => _svc.getCases();

  Future<Case> createCase(String title) async {
    final c = await _svc.createCase(title);
    state = AsyncData([c, ...state.valueOrNull ?? []]);
    return c;
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => _svc.getCases());
  }

  void updateCaseLocally(Case updatedCase) {
    final current = state.valueOrNull ?? [];
    state = AsyncData(
      current.map((c) => c.id == updatedCase.id ? updatedCase : c).toList(),
    );
  }
}

final casesProvider = AsyncNotifierProvider<CasesNotifier, List<Case>>(CasesNotifier.new);

// ── Single case ─────────────────────────────────────────────────────────────

final singleCaseProvider =
    FutureProvider.family<Case, String>((ref, caseId) async {
  final svc = CaseService();
  return svc.getCase(caseId);
});

// ── Chat messages ────────────────────────────────────────────────────────────

class ChatNotifier extends FamilyAsyncNotifier<List<ChatMessage>, String> {
  late CaseService _svc;

  @override
  Future<List<ChatMessage>> build(String caseId) async {
    _svc = CaseService();
    return _svc.getChatMessages(caseId);
  }

  Future<Case> sendMessage(String content) async {
    final caseId = arg;
    final current = state.valueOrNull ?? [];
    // Optimistic update: add user message immediately
    final tempMsg = ChatMessage(
      id: 'temp-${DateTime.now().millisecondsSinceEpoch}',
      role: MessageRole.user,
      content: content,
      createdAt: DateTime.now(),
    );
    state = AsyncData([...current, tempMsg]);

    final result = await _svc.sendMessage(caseId, content);
    state = AsyncData([
      ...current,
      ChatMessage(
        id: result.message.id,
        role: MessageRole.user,
        content: content,
        createdAt: result.message.createdAt,
      ),
      result.message,
    ]);
    return result.updatedCase;
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => _svc.getChatMessages(arg));
  }
}

final chatProvider =
    AsyncNotifierProviderFamily<ChatNotifier, List<ChatMessage>, String>(ChatNotifier.new);

// ── Process score ────────────────────────────────────────────────────────────

final scoreProvider =
    FutureProvider.family<ProcessScore?, String>((ref, caseId) async {
  final svc = CaseService();
  return svc.getCaseScore(caseId);
});
