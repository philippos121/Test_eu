class CaseDocument {
  final String id;
  final String filename;
  final String docType;
  final DateTime createdAt;

  const CaseDocument({
    required this.id,
    required this.filename,
    required this.docType,
    required this.createdAt,
  });

  factory CaseDocument.fromJson(Map<String, dynamic> j) => CaseDocument(
        id: j['id'] as String,
        filename: j['filename'] as String,
        docType: j['doc_type'] as String,
        createdAt: DateTime.parse(j['created_at'] as String),
      );

  bool get isFormA => docType == 'form_a';
  String get typeLabel => isFormA ? 'Formular A (EU-Klage)' : 'Gerichtsdokument';
}
