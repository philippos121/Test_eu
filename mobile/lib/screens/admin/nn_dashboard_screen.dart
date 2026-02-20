import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:percent_indicator/linear_percent_indicator.dart';
import '../../models/statistics.dart';
import '../../services/statistics_service.dart';
import '../../theme.dart';
import '../../widgets/common.dart';

// ── Providers ─────────────────────────────────────────────────────────────────

final _nnStatusProvider = FutureProvider<Map<String, dynamic>?>(
    (_) => StatisticsService().getNNStatus());

final _nnSummaryProvider =
    FutureProvider<NNDataSummary>((_) => StatisticsService().getNNDataSummary());

final _nnPredictionsProvider =
    FutureProvider<List<Map<String, dynamic>>>((_) => StatisticsService().getNNPredictions());

// ── Screen ────────────────────────────────────────────────────────────────────

class NNDashboardScreen extends ConsumerStatefulWidget {
  const NNDashboardScreen({super.key});
  @override
  ConsumerState<NNDashboardScreen> createState() => _NNDashboardScreenState();
}

class _NNDashboardScreenState extends ConsumerState<NNDashboardScreen> {
  int _epochs = 300;
  double _lr = 0.005;
  double _l2 = 0.0001;
  int _batchSize = 16;
  bool _training = false;
  String? _trainMsg;
  bool _trainSuccess = false;

  Future<void> _startTraining() async {
    setState(() { _training = true; _trainMsg = null; });
    try {
      final result = await StatisticsService().trainNN(
        epochs: _epochs, lr: _lr, l2: _l2, batchSize: _batchSize,
      );
      final success = result['success'] as bool? ?? false;
      setState(() {
        _trainSuccess = success;
        _trainMsg = success
            ? '✓ v${result['version']} | Train: ${((result['train_accuracy'] as num?)?.toDouble() ?? 0) * 100:.0f}% | Val: ${((result['val_accuracy'] as num?)?.toDouble() ?? 0) * 100:.0f}%'
            : result['message'] as String? ?? 'Fehler';
      });
      if (success) {
        ref.invalidate(_nnStatusProvider);
        ref.invalidate(_nnSummaryProvider);
        ref.invalidate(_nnPredictionsProvider);
      }
    } catch (e) {
      setState(() { _trainSuccess = false; _trainMsg = e.toString(); });
    } finally {
      setState(() => _training = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final statusAsync = ref.watch(_nnStatusProvider);
    final summaryAsync = ref.watch(_nnSummaryProvider);
    final predictionsAsync = ref.watch(_nnPredictionsProvider);

    return Scaffold(
      backgroundColor: AppTheme.surface,
      appBar: AppBar(title: const Text('Neuronales Netz')),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(_nnStatusProvider);
          ref.invalidate(_nnSummaryProvider);
          ref.invalidate(_nnPredictionsProvider);
        },
        color: AppTheme.primary,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            // Architecture info
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.primary.withOpacity(0.06),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppTheme.primary.withOpacity(0.15)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Architektur: 40 → 32 → 16 → 3 (Softmax)',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppTheme.primary)),
                const SizedBox(height: 2),
                const Text('Adam (β₁=0.9, β₂=0.999) · Kategorische Kreuzentropie (CCE)',
                    style: TextStyle(fontSize: 11, color: Colors.grey)),
                const SizedBox(height: 2),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: Colors.green.shade50,
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: Colors.green.shade200),
                  ),
                  child: const Text('⚙ Training läuft serverseitig in Python/NumPy',
                      style: TextStyle(fontSize: 10, color: Colors.green, fontWeight: FontWeight.w600)),
                ),
              ]),
            ).animate().fadeIn(),
            const SizedBox(height: 12),

            // Data summary
            summaryAsync.when(
              loading: () => const LoadingCenter(),
              error: (e, _) => ErrorCenter(error: e),
              data: (s) => _DataSummaryGrid(summary: s).animate().fadeIn(delay: 100.ms),
            ),
            const SizedBox(height: 12),

            // Active model
            statusAsync.when(
              loading: () => const SizedBox.shrink(),
              error: (e, _) => const SizedBox.shrink(),
              data: (model) => model == null
                  ? Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: const Text('Kein Modell trainiert.',
                            style: TextStyle(color: Colors.grey), textAlign: TextAlign.center),
                      ),
                    ).animate().fadeIn()
                  : _ModelCard(model: model).animate().fadeIn(delay: 150.ms),
            ),
            const SizedBox(height: 12),

            // Training controls
            _TrainingPanel(
              epochs: _epochs,
              lr: _lr,
              l2: _l2,
              batchSize: _batchSize,
              training: _training,
              trainMsg: _trainMsg,
              trainSuccess: _trainSuccess,
              onEpochsChanged: (v) => setState(() => _epochs = v),
              onLrChanged: (v) => setState(() => _lr = v),
              onL2Changed: (v) => setState(() => _l2 = v),
              onBatchSizeChanged: (v) => setState(() => _batchSize = v),
              onTrain: _startTraining,
            ).animate().fadeIn(delay: 200.ms),
            const SizedBox(height: 12),

            // Loss chart (from model)
            statusAsync.when(
              loading: () => const SizedBox.shrink(),
              error: (_, __) => const SizedBox.shrink(),
              data: (model) {
                final history = model?['training_history'] as List?;
                if (history == null || history.isEmpty) return const SizedBox.shrink();
                return _LossChart(history: history.cast<Map<String, dynamic>>())
                    .animate().fadeIn(delay: 300.ms);
              },
            ),
            const SizedBox(height: 12),

            // Feature importance
            statusAsync.when(
              loading: () => const SizedBox.shrink(),
              error: (_, __) => const SizedBox.shrink(),
              data: (model) {
                final fi = model?['feature_importance'] as List?;
                if (fi == null || fi.isEmpty) return const SizedBox.shrink();
                return _FeatureImportance(features: fi.cast<Map<String, dynamic>>())
                    .animate().fadeIn(delay: 350.ms);
              },
            ),
            const SizedBox(height: 12),

            // Predictions table
            predictionsAsync.when(
              loading: () => const SizedBox.shrink(),
              error: (_, __) => const SizedBox.shrink(),
              data: (preds) => preds.isEmpty
                  ? const SizedBox.shrink()
                  : _PredictionsTable(predictions: preds).animate().fadeIn(delay: 400.ms),
            ),
            const SizedBox(height: 80),
          ]),
        ),
      ),
    );
  }
}

// ── Data Summary Grid ─────────────────────────────────────────────────────────

class _DataSummaryGrid extends StatelessWidget {
  final NNDataSummary summary;
  const _DataSummaryGrid({required this.summary});

  @override
  Widget build(BuildContext context) {
    final items = [
      ('Gelabelte Fälle', '${summary.nLabeledCases}', AppTheme.primary),
      ('Klasse 0 (Vollerfolg)', '${summary.nClass0}', AppTheme.success),
      ('Klasse 1 (Teilerfolg)', '${summary.nClass1}', AppTheme.warning),
      ('Klasse 2 (Misserfolg)', '${summary.nClass2}', AppTheme.danger),
      ('Features', '${summary.nFeatures}', AppTheme.primary),
      ('NN-Blend (max 30%)', '${(summary.blendWeight * 100).toStringAsFixed(0)}%', AppTheme.primary),
    ];
    return GridView.count(
      crossAxisCount: 3,
      mainAxisSpacing: 8,
      crossAxisSpacing: 8,
      childAspectRatio: 1.3,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      children: items.map((item) => Card(
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Text(item.$2,
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: item.$3)),
            const SizedBox(height: 2),
            Text(item.$1,
                style: const TextStyle(fontSize: 9, color: Colors.grey),
                textAlign: TextAlign.center, maxLines: 2),
          ]),
        ),
      )).toList(),
    );
  }
}

// ── Model Card ────────────────────────────────────────────────────────────────

class _ModelCard extends StatelessWidget {
  final Map<String, dynamic> model;
  const _ModelCard({required this.model});

  @override
  Widget build(BuildContext context) {
    final trainAcc = (model['train_accuracy'] as num?)?.toDouble() ?? 0;
    final valAcc = (model['val_accuracy'] as num?)?.toDouble() ?? 0;
    final hp = model['hyperparams'] as Map<String, dynamic>? ?? {};

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.memory, size: 18, color: AppTheme.primary),
            const SizedBox(width: 6),
            Text('Aktives Modell — v${model['version']}',
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.primary)),
          ]),
          const SizedBox(height: 12),
          Wrap(spacing: 24, runSpacing: 12, children: [
            _MetaChip('Train-Acc', '${(trainAcc * 100).toStringAsFixed(1)}%',
                trainAcc >= 0.75 ? AppTheme.success : trainAcc >= 0.6 ? AppTheme.warning : AppTheme.danger),
            _MetaChip('Val-Acc', '${(valAcc * 100).toStringAsFixed(1)}%',
                valAcc >= 0.75 ? AppTheme.success : valAcc >= 0.6 ? AppTheme.warning : AppTheme.danger),
            _MetaChip('Epochen', '${hp['epochs'] ?? '—'}', AppTheme.primary),
            _MetaChip('Lernrate', '${hp['lr'] ?? '—'}', AppTheme.primary),
            _MetaChip('Train-Fälle', '${model['n_train_cases'] ?? '—'}', AppTheme.primary),
            _MetaChip('Val-Fälle', '${model['n_val_cases'] ?? '—'}', AppTheme.primary),
          ]),
        ]),
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _MetaChip(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 10, color: Colors.grey)),
          Text(value, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: color)),
        ],
      );
}

// ── Training Panel ────────────────────────────────────────────────────────────

class _TrainingPanel extends StatelessWidget {
  final int epochs;
  final double lr;
  final double l2;
  final int batchSize;
  final bool training;
  final String? trainMsg;
  final bool trainSuccess;
  final ValueChanged<int> onEpochsChanged;
  final ValueChanged<double> onLrChanged;
  final ValueChanged<double> onL2Changed;
  final ValueChanged<int> onBatchSizeChanged;
  final VoidCallback onTrain;

  const _TrainingPanel({
    required this.epochs, required this.lr, required this.l2, required this.batchSize,
    required this.training, required this.trainMsg, required this.trainSuccess,
    required this.onEpochsChanged, required this.onLrChanged, required this.onL2Changed,
    required this.onBatchSizeChanged, required this.onTrain,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Training starten',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.primary)),
          const SizedBox(height: 4),
          const Text(
            'Adam aktualisiert W₁(40×32), W₂(32×16), W₃(16×3) · ∇Z = (ŷ − y)/m',
            style: TextStyle(fontSize: 10, color: Colors.grey),
          ),
          const SizedBox(height: 14),
          // Hyperparameter sliders
          Row(children: [
            const Text('Epochen: ', style: TextStyle(fontSize: 12)),
            Text('$epochs', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppTheme.primary)),
          ]),
          Slider(
            value: epochs.toDouble(),
            min: 50, max: 1000, divisions: 19,
            activeColor: AppTheme.primary,
            onChanged: (v) => onEpochsChanged(v.round()),
          ),
          const SizedBox(height: 8),
          Row(children: [
            const Expanded(child: _DropdownParam<double>(
              label: 'Lernrate', value: 0.005,
              items: {0.01: '0.010', 0.005: '0.005', 0.002: '0.002', 0.001: '0.001'},
            )),
            const SizedBox(width: 16),
            const Expanded(child: _DropdownParam<int>(
              label: 'Batch-Größe', value: 16,
              items: {8: '8', 16: '16', 32: '32'},
            )),
          ]),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: training ? null : onTrain,
              icon: training
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                  : const Icon(Icons.play_arrow),
              label: Text(training ? 'Training läuft auf Server…' : 'Training starten'),
            ),
          ),
          if (trainMsg != null) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: trainSuccess ? AppTheme.success.withOpacity(0.08) : AppTheme.danger.withOpacity(0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(trainMsg!,
                  style: TextStyle(
                      fontSize: 12,
                      color: trainSuccess ? AppTheme.success : AppTheme.danger)),
            ),
          ],
        ]),
      ),
    );
  }
}

class _DropdownParam<T> extends StatelessWidget {
  final String label;
  final T value;
  final Map<T, String> items;
  const _DropdownParam({required this.label, required this.value, required this.items});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 11, color: Colors.grey)),
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey.shade300),
              borderRadius: BorderRadius.circular(8),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<T>(
                value: value,
                isExpanded: true,
                style: const TextStyle(fontSize: 13, color: Colors.black87),
                items: items.entries
                    .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                    .toList(),
                onChanged: (_) {},
              ),
            ),
          ),
        ],
      );
}

// ── Loss Chart ────────────────────────────────────────────────────────────────

class _LossChart extends StatelessWidget {
  final List<Map<String, dynamic>> history;
  const _LossChart({required this.history});

  @override
  Widget build(BuildContext context) {
    if (history.isEmpty) return const SizedBox.shrink();

    final trainSpots = history.asMap().entries.map((e) =>
        FlSpot(e.key.toDouble(), (e.value['train_loss'] as num?)?.toDouble() ?? 0)).toList();
    final valSpots = history.asMap().entries.map((e) =>
        FlSpot(e.key.toDouble(), (e.value['val_loss'] as num?)?.toDouble() ?? 0)).toList();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Loss-Verlauf (CCE)',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.primary)),
          const SizedBox(height: 4),
          const Text('Blau = Train-Loss · Orange = Val-Loss',
              style: TextStyle(fontSize: 10, color: Colors.grey)),
          const SizedBox(height: 12),
          SizedBox(
            height: 150,
            child: LineChart(
              LineChartData(
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (_) =>
                      FlLine(color: Colors.grey.shade200, strokeWidth: 1),
                ),
                titlesData: FlTitlesData(
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 36,
                      getTitlesWidget: (v, _) => Text('${v.toStringAsFixed(1)}',
                          style: const TextStyle(fontSize: 9, color: Colors.grey)),
                    ),
                  ),
                  bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
                ),
                borderData: FlBorderData(show: false),
                lineBarsData: [
                  LineChartBarData(
                    spots: trainSpots,
                    isCurved: true,
                    color: AppTheme.primary,
                    barWidth: 2,
                    dotData: const FlDotData(show: false),
                  ),
                  LineChartBarData(
                    spots: valSpots,
                    isCurved: true,
                    color: AppTheme.warning,
                    barWidth: 2,
                    dotData: const FlDotData(show: false),
                    dashArray: [4, 4],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          // Epoch table (first 3 + last 2)
          _EpochTable(history: history),
        ]),
      ),
    );
  }
}

class _EpochTable extends StatelessWidget {
  final List<Map<String, dynamic>> history;
  const _EpochTable({required this.history});

  @override
  Widget build(BuildContext context) {
    final rows = [
      ...history.take(3),
      if (history.length > 5) null, // separator
      ...history.skip(history.length > 3 ? history.length - 2 : 0),
    ];

    return Table(
      columnWidths: const {
        0: FixedColumnWidth(56),
        1: FlexColumnWidth(),
        2: FlexColumnWidth(),
        3: FlexColumnWidth(),
        4: FlexColumnWidth(),
      },
      defaultVerticalAlignment: TableCellVerticalAlignment.middle,
      children: [
        TableRow(
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFE0E0E0)))),
          children: ['Epoche', 'Train-Loss', 'Val-Loss', 'Train-Acc', 'Val-Acc']
              .map((t) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Text(t, style: const TextStyle(fontSize: 9, color: Colors.grey, fontWeight: FontWeight.w600)),
                  ))
              .toList(),
        ),
        ...rows.where((r) => r != null).cast<Map<String, dynamic>>().map((h) {
          final ta = (h['train_acc'] as num?)?.toDouble() ?? 0;
          final va = (h['val_acc'] as num?)?.toDouble() ?? 0;
          return TableRow(children: [
            _cell('${h['epoch']}'),
            _cell((h['train_loss'] as num?)?.toDouble().toStringAsFixed(4) ?? '—'),
            _cell((h['val_loss'] as num?)?.toDouble().toStringAsFixed(4) ?? '—'),
            _cell('${(ta * 100).toStringAsFixed(0)}%',
                color: ta >= 0.75 ? AppTheme.success : ta >= 0.6 ? AppTheme.warning : AppTheme.danger),
            _cell('${(va * 100).toStringAsFixed(0)}%',
                color: va >= 0.75 ? AppTheme.success : va >= 0.6 ? AppTheme.warning : AppTheme.danger),
          ]);
        }),
      ],
    );
  }

  Widget _cell(String text, {Color? color}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Text(text,
            style: TextStyle(fontSize: 10, color: color ?? Colors.black87, fontWeight: color != null ? FontWeight.w600 : FontWeight.normal)),
      );
}

// ── Feature Importance ────────────────────────────────────────────────────────

class _FeatureImportance extends StatelessWidget {
  final List<Map<String, dynamic>> features;
  const _FeatureImportance({required this.features});

  @override
  Widget build(BuildContext context) {
    final maxVal = features.fold(0.0,
        (m, f) => m < ((f['importance'] as num?)?.toDouble() ?? 0) ? (f['importance'] as num).toDouble() : m);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Feature-Wichtigkeit (Ø |W₁|)',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.primary)),
          const SizedBox(height: 4),
          const Text('Spalte W₁ (40×32): hohe Werte = starker Einfluss',
              style: TextStyle(fontSize: 10, color: Colors.grey)),
          const SizedBox(height: 12),
          ...features.asMap().entries.take(15).map((e) {
            final i = e.key;
            final f = e.value;
            final name = f['name'] as String? ?? '';
            final importance = (f['importance'] as num?)?.toDouble() ?? 0;
            final pct = maxVal > 0 ? importance / maxVal : 0.0;
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                SizedBox(
                  width: 20,
                  child: Text('${i + 1}', style: const TextStyle(fontSize: 9, color: Colors.grey)),
                ),
                Expanded(
                  flex: 3,
                  child: Text(name,
                      style: const TextStyle(fontSize: 10),
                      overflow: TextOverflow.ellipsis),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 4,
                  child: LinearPercentIndicator(
                    percent: pct.clamp(0.0, 1.0),
                    lineHeight: 8,
                    backgroundColor: Colors.grey.shade200,
                    progressColor: i < 3 ? AppTheme.primary : Colors.blue.shade200,
                    barRadius: const Radius.circular(4),
                    padding: EdgeInsets.zero,
                  ),
                ),
                const SizedBox(width: 6),
                Text(importance.toStringAsFixed(4),
                    style: const TextStyle(fontSize: 9, color: Colors.grey)),
              ]),
            );
          }),
        ]),
      ),
    );
  }
}

// ── Predictions Table ─────────────────────────────────────────────────────────

class _PredictionsTable extends StatelessWidget {
  final List<Map<String, dynamic>> predictions;
  const _PredictionsTable({required this.predictions});

  @override
  Widget build(BuildContext context) {
    final correct = predictions.where((p) => p['correct'] == true).length;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Expanded(
              child: Text('NN-Vorhersagen (3-Klassen)',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.primary)),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: AppTheme.success.withOpacity(0.1),
                borderRadius: BorderRadius.circular(5),
              ),
              child: Text('$correct / ${predictions.length} korrekt',
                  style: const TextStyle(fontSize: 11, color: AppTheme.success, fontWeight: FontWeight.w600)),
            ),
          ]),
          const SizedBox(height: 4),
          const Text('Grün = richtige Klasse · 0=Vollerfolg · 1=Teilerfolg · 2=Misserfolg',
              style: TextStyle(fontSize: 10, color: Colors.grey)),
          const SizedBox(height: 12),
          ...predictions.map((p) {
            final isCorrect = p['correct'] as bool? ?? false;
            final pNn = (p['p_nn'] as num?)?.toDouble() ?? 0;
            final actual = p['actual_label'] as String? ?? '—';
            final predicted = p['predicted_label'] as String? ?? '—';
            final title = p['case_title'] as String? ?? '—';
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              margin: const EdgeInsets.only(bottom: 4),
              decoration: BoxDecoration(
                color: isCorrect ? const Color(0xFFF1F8E9) : const Color(0xFFFCE4EC),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(children: [
                Text(isCorrect ? '✓' : '✗',
                    style: TextStyle(
                        fontSize: 13,
                        color: isCorrect ? AppTheme.success : AppTheme.danger,
                        fontWeight: FontWeight.w700)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(title,
                      style: const TextStyle(fontSize: 11),
                      overflow: TextOverflow.ellipsis),
                ),
                const SizedBox(width: 8),
                Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text('${(pNn * 100).toStringAsFixed(0)}% p_NN',
                      style: TextStyle(
                          fontSize: 10,
                          color: pNn >= 0.5 ? AppTheme.success : AppTheme.danger,
                          fontWeight: FontWeight.w600)),
                  Text('Vorh.: $predicted · Ist: $actual',
                      style: const TextStyle(fontSize: 9, color: Colors.grey)),
                ]),
              ]),
            );
          }),
        ]),
      ),
    );
  }
}
