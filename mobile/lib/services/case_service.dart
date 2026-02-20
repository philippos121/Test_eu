import 'package:dio/dio.dart';

import '../config/api_config.dart';
import '../models/case.dart';
import '../models/chat_message.dart';
import '../models/document.dart';
import '../models/process_score.dart';
import 'api_client.dart';

class CaseService {
  final _api = ApiClient.instance;

  Future<List<Case>> getCases() async {
    final res = await _api.get<List<dynamic>>(ApiConfig.casesPath);
    return res.data!.map((e) => Case.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Case> createCase(String title) async {
    final res = await _api.post<Map<String, dynamic>>(
      ApiConfig.casesPath,
      data: {'title': title},
    );
    return Case.fromJson(res.data!);
  }

  Future<Case> getCase(String caseId) async {
    final res = await _api.get<Map<String, dynamic>>('${ApiConfig.casesPath}/$caseId');
    return Case.fromJson(res.data!);
  }

  Future<Case> updateCase(String caseId, Map<String, dynamic> updates) async {
    final res = await _api.patch<Map<String, dynamic>>(
      '${ApiConfig.casesPath}/$caseId',
      data: updates,
    );
    return Case.fromJson(res.data!);
  }

  Future<ProcessScore?> getCaseScore(String caseId) async {
    final res = await _api.get<dynamic>('${ApiConfig.casesPath}/$caseId/score');
    if (res.data == null) return null;
    return ProcessScore.fromJson(res.data as Map<String, dynamic>);
  }

  Future<List<ChatMessage>> getChatMessages(String caseId) async {
    final res = await _api.get<List<dynamic>>('${ApiConfig.casesPath}/$caseId/chat');
    return res.data!.map((e) => ChatMessage.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<({ChatMessage message, Case updatedCase})> sendMessage(
      String caseId, String content) async {
    final res = await _api.post<Map<String, dynamic>>(
      '${ApiConfig.casesPath}/$caseId/chat',
      data: {'content': content},
    );
    final data = res.data!;
    return (
      message: ChatMessage.fromJson(data['message'] as Map<String, dynamic>),
      updatedCase: Case.fromJson(data['case'] as Map<String, dynamic>),
    );
  }

  Future<List<CaseDocument>> getDocuments(String caseId) async {
    final res =
        await _api.get<List<dynamic>>('${ApiConfig.casesPath}/$caseId/documents');
    return res.data!
        .map((e) => CaseDocument.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<CaseDocument> generateFormA(String caseId) async {
    final res = await _api.post<Map<String, dynamic>>(
      '${ApiConfig.casesPath}/$caseId/documents/generate-form-a',
    );
    return CaseDocument.fromJson(res.data!);
  }

  Future<CaseDocument> uploadDocument(String caseId, String filePath,
      String filename, String docType) async {
    final res = await _api.postForm<Map<String, dynamic>>(
      '${ApiConfig.casesPath}/$caseId/documents/upload',
      formData: {
        'file': await MultipartFile.fromFile(filePath, filename: filename),
        'doc_type': docType,
      },
    );
    return CaseDocument.fromJson(res.data!);
  }

  Future<String> getDocumentDownloadUrl(String caseId, String docId) =>
      _api.downloadUrl('${ApiConfig.casesPath}/$caseId/documents/$docId/download');
}
