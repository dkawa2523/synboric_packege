# ml_platform_symbolic — 実装仕様・手法選定・事前学習設計

| 項目 | 内容 |
| --- | --- |
| バージョン | v0.5 / 2026-10-25 |
| 目的 | コーディングエージェントが小さな実装から完成させられる関数同定基盤 |
| 対象 | `ml_platform` / `agent/quality-gates`。前回の実コード確認基準は`91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0` |
| 配布名 / import | `ml-platform-symbolic` / `ml_platform_symbolic` |
| 状態 | 実装設計。探索基盤・各Engine・ClearML接続は未実装。添付の外部データ準備スクリプトは実行確認済み |

## 1. コーディングエージェントが最初に読むこと

**最初に作るのは、データを読み、二つの探索法の候補を共通評価し、選択式を保存・ロードして予測できる一本の経路である。** 10手法を同時に実装したり、先に汎用プラグイン基盤を作ったりしない。

| この文書の範囲 | 読む場面 |
| --- | --- |
| 1–9章：実装の本則 | 毎回の設計・変更判断。必要な型、責務、実装順、最低限の検証 |
| 10章：調査と優先10手法 | Adapterの追加・手法選択 |
| 11章：事前学習3手法の詳細 | Flash-ANSR、RASR、PISRの実装時だけ参照 |
| 12章：既存コードと一次資料 | 既存基盤の接続箇所の確認 |
| `AGENTS.md` | エージェントの汎用的な実装ルール。既存rootの指示を上書きせず統合して使う |
| `VALIDATION_DATASETS.md` | 実行済みデータ、分割、試験用途、取得・再現コマンド |

共通型・ID・診断は少数に限定する。旧版のクラス名を一つずつ実装する必要はない。数式の意味、データ分割、単位、固定係数、保存後予測を守る処理は残す。10–11章の詳細な記録候補は、以下の本則に従い必要時だけ実装する。実装の判断が競合したら1–9章を優先する。

実装者レビューで、未確定だったAST、設定名、Stage引数、bundle参照、例外処理を以下で確定した。3章のAPI、4章のJSON、6章のファイルとYAMLを実装の正本とし、別名・第二の形式を増やさない。ここで確定するのは自パッケージのAPIであり、未検証のnative APIを動作済みとは扱わない。

## 2. コード構成と責務

```text
pkgs/symbolic/src/ml_platform_symbolic/
  __init__.py          # 公開: run_task, load_model
  manifest.py          # 公開パラメータとTask/Stage/Artifact名
  config.py            # preset、設定解決、境界の検証
  domain_plan.py       # SDKを含まない実行計画
  stage.py             # prepare/discover/compare/finalize/inferの薄い振分け
  data.py              # 数値表、列・単位、固定splitの読込
  expressions.py       # 小さなJSON ASTの検査・数値実行・表示・hash
  constraints.py       # 対応する制約だけを明示的に検査
  fitting.py           # 自由係数だけの最小二乗fit
  evaluation.py        # 共通誤差・複雑度・候補選択
  model.py             # bundleの保存・ロード・推論
  reporting.py         # 表・図・結果要約のファイル生成
  assets.py            # 事前学習資産のローカル完全性検査。必要になって追加
  engines/
    base.py            # 小さな共通入出力
    registry.py        # 名前→遅延import。静的dictで十分
    runner.py          # 探索プロセス・時間制限・終了処理
    pysr.py            # 各native APIとの変換
    physo.py
```

後続Adapterは同じengines配下へ追加する。PySIPSのposteriorやPISRのsource bridgeが大きくなった場合だけ、そのEngineをサブディレクトリへ分ける。`runtime.py`、`selection.py`、`bundle.py`、`inference.py`等への分割は実装量を見て行い、初期から細分化しない。

| 所有者 | 一つの責務 | 境界 |
| --- | --- | --- |
| symbolic/data | データの標準化・分割 | 探索・係数fitを行わない |
| 各Adapter | 探索・native設定・AST export・native照合 | 他Engineの順位付け、Selection/Finalの参照、SDK操作を行わない |
| expressions/constraints | 保存可能な式の意味と適格性 | nativeライブラリへ依存しない |
| fitting/evaluation | 共通fit・評価・選定 | native lossを共通指標に使わない |
| model | 採用した式をそのまま保存・実行 | 推論時に再探索・自動refitしない |
| reporting | 結果を表示用ファイルへ変換 | 評価や選定を再計算しない |
| spdml_layer | Dataset取得、DAG、SDK、転送、Registry、推論Draft | 数式の数値・物理ロジックを持たない |
| core | 既存のIO・設定・結果・小さな共通レコード | symbolic固有のAST・制約・探索型を移さない |

`symbolic → core`、`tabular → core`。相互依存は禁止。ローカルとClearMLは同じStage関数を使う。エントリポイント・scriptsへ業務ロジックを複製しない。

## 3. 最低限の共通データとAPI

既存`PackageManifest`、`DomainStepPlan`、`RunResult`を使う。symbolic固有の公開レコードは次の程度から始め、細かなRecordクラスを増やさない。

| レコード | 最低限の中身 |
| --- | --- |
| `DiscoveryRequest` | `X`: float64の(n,p)配列、`y`: (n,)配列、`row_ids`: 行ID列、`variables`: Xの列順に並ぶ定義dict列、`target`: 定義dict、`operators`: 演算名列、`limits`: 上限dict、`seed`: int、`options`: native用dict |
| `DiscoveryContext` | `work_dir`: Path、`device`: str、`assets_dir`: PathまたはNone |
| `Candidate` | `candidate_id`: str、`engine`: str、`seed`: int、`equation`: 4.3節のdict、`native_check`: passed/n_points/max_abs_errorのdict |
| `DiscoveryResult` | `candidates`: Candidate列、`status`: ok/failed/timeout、`summary`: 件数・時間・任意reasonのdict |

```python
class DiscoveryEngine(Protocol):
    def capabilities(self) -> dict: ...
    def discover(self, request: DiscoveryRequest,
                 context: DiscoveryContext) -> DiscoveryResult: ...
```

能力宣言dictの基本キーは`operators`、`constraints`、`requires_assets`だけとする。checkpoint固有の入力上限はasset manifestに置く。汎用capability plannerやプラグイン依存解決器は作らない。選んだAdapterを遅延importし、nativeライブラリのimportはdiscover内で行う。Controllerでのprepareは設定・宣言だけを検査し、探索Workerで依存版・asset・native対応を再確認する。EngineCapabilitiesという別型は設けない。

変数定義の最小キーは`id`（x0等）、`column`（元の列名）、`unit`（既知の単位文字列またはnull）。targetもcolumn/unitを持つ。配列の列順はvariablesが定義し、Adapterが勝手に並べ替えない。candidate_idは`engine/seed/index`でRun内一意にする。共通refit後の候補も同じID＋fit_variantで追跡する。

評価結果はDataFrame/CSV、Engine固有情報はdictで十分。`CandidateDraft`、`EvaluationRecord`、`ConstraintCoverage`等を初期の公開型として増やさない。nativeオブジェクトはWorker内だけで扱い、Stage間にはJSON/CSV/数値ファイルを渡す。

## 4. データ・数式の正しさ

### 4.1 分割

- 数値列・有限値・欠損なし・単一ターゲットから開始。カテゴリ変換、自動補完、目的変数の対数化は行わない。
- splitはprepareで一度決め、全Engineに同じtrainを渡す。Selectionは共通選定、Finalは選定・fit方針凍結後の評価に限る。
- 外部で作った`split.csv`を読めるようにする。行IDによる対応を検査し、固定splitを勝手にrandomへ変えない。
- group分割では同一実験・設計を跨がせない。ID/group/time列は特徴から除外する。
- 既存tabularの`valid_size=0.2`、残りに対する`selection_size=0.2`は全体で64/16/20。groupでは実件数が変わるため件数を示す。
- 小規模データには独立Finalなしのexploratoryを明示。CV・Bootstrapを初期の必須機能にしない。

### 4.2 数式と係数

実行の正本は許可された小さなJSON AST。ノードはvariable/literal/parameter/operator、演算はRunが必要とする四則・整数べき等から追加する。任意`eval`や任意関数呼出しは使わない。数式文字列の見た目だけでnativeとの一致を判断しない。

1. Adapterでnative予測と共通AST予測をtrainの固定検査点で照合する。必要な定義域probeは少数の明示点とする。
2. protected log/div等、標準化、列順、全精度の係数を保つ。再現できない式は不適格にする。
3. 固定指数・物理定数・単位換算値と自由係数を区別する。自由係数だけをfitする。
4. `x/x→1`等の定義域を変える自動簡約を行わない。式を修復するための隠れたabs/clipを挿入しない。
5. NaN/Inf/未定義点がある候補について、良い行だけのRMSEを計算しない。

単位は入力/canonical/次元を記録し、℃→K等の換算を再現できるようにする。単位不明はunknownとし、無次元とみなさない。PhySOの初期Adapterは必要な既知単位を要求し、不足時は指定方法を示して停止する。AirfoilのdBのような対数量は単純な圧力単位へ変換しない。

初期制約は演算・変数・最大式サイズ、係数bounds、次元検査、明示probeでの有限値・応答範囲まで。各制約はrequiredと検査方法、pass/fail/unknownを持つ小さなdictでよい。必須unknownは採用不可。標本点でのpassを全域保証と表示しない。一般保存則DSL・証明エンジン・自動次元推論基盤は後回しにする。

### 4.3 AST v1の最小形式

式dictは`schema_version`、`ast`、`parameters`を持つ。最初に演算子の意味と保存形式を実装し、それに対応するnative式だけをexportする。別のExprクラス階層や文字列形式との二重管理はしない。

```json
{
  "schema_version": 1,
  "ast": {"op": "add", "args": [
    {"op": "mul", "args": [{"param": "a"}, {"var": "x0"}]},
    {"const": 1.0}
  ]},
  "parameters": {
    "a": {"value": 2.0, "trainable": true, "bounds": [0.0, null], "unit": null}
  }
}
```

葉はvar/const/paramのいずれか一つ、内部ノードはop/argsだけを持つ。varはvariablesのid、paramはparametersのkeyを参照する。constは有限実数、parameter.valueも有限実数。boundsは[lower,upper]でnullは無限側。同じparam名の複数出現は同じ自由係数である。

初期演算はadd/sub/mul/div（2引数）、neg（1引数）、pow_int（2引数）。pow_intの第2引数は固定整数constで[-8,8]に限定する。必要になってからsqrt/log/exp/absを追加し、sqrtはx>=0、logはx>0を実数定義域とする。divの分母はゼロ不可。overflowや非有限値は無効。clipやprotected版は別の意味として明示実装するまで拒否する。

Runtimeはfloat64で(n,p)入力から(n,)を返し、定数式はn行へbroadcastする。初期上限は100ノード、深さ20。未知op・参照欠落・不正arity・上限超過をロード時に拒否する。Runのmax_nodesはこの上限以下で指定する。node数は葉も含む出現回数で数え、distinct自由係数数はtrainableなparam名の種類数とする。

native照合はtrainからseed固定で最大64行を取り、nativeとASTの有限maskを比較する。mask不一致または有限な比較点0件は不合格。有効点では`rtol=1e-5`、`atol=1e-7*max(std(y_train),1e-12)`を初期規則として保存する。定義域での安全性や全行の有限性はcompareで別に確認する。許容差を変える場合はRun開始前に設定し、結果を通すために事後変更しない。

自由係数の次元が取得できない場合、unitはnullのままとする。初期版で次元を推測して埋めない。単位制約を必須にしたRunで未解決なら不適格。構文・係数・次元チェックとprobeでの応答検査は別々に記録する。

## 5. 共通評価とモデル選択

### 5.1 評価と選定

同じSelection行・単位・重みでRMSE/MAE/R²を計算し、式サイズと自由係数数を併記する。定数ターゲットでのR²等、未定義指標はnullと理由を残す。初期の重みは行等重み。group等重みは必要になって明示追加する。

式サイズはASTノード数から始める。native complexity、loss、生成確率は診断用。必須制約とnative照合を通った候補からPareto（RMSE・サイズ）を作り、標準で1式を採用する。

max_export_candidatesは**共通Selectionへ投入する上限**であり、表示件数ではない。nativeから取得できた候補集合とその切詰め方法をsummaryへ記録する。上限を超えたexport済み候補はrunnerが共通Runtimeのtrain RMSE→node数→候補IDで並べて切り詰める。計算はevaluation.pyの共通関数を再利用し、Adapterごとに評価器を実装しない。Selectionを見て投入候補を増減しない。異なるnative候補数・関数空間を持つ手法が完全同条件になるとは主張しない。

`balanced`：最小Selection RMSEをrとし、`RMSE <= r*(1+relative_tolerance)+absolute_tolerance`の候補から、サイズ→RMSE→自由係数数→候補IDの順で選ぶ。既定はrelative 0.05、absolute 0。これは業務の合格精度ではない。`accuracy`はRMSE優先。`simplicity`は事前の許容RMSE指定を必須とする。

### 5.2 係数fit

`none`はnative係数を保持する。`bounded_least_squares`は比較前にtrainだけで自由係数を共通fitし、凍結した代表式をtrain＋Selectionで最終fitする。固定リテラルと構造は変えない。fit失敗や必須制約違反は不適格とし、失敗候補だけnative係数へ戻すfallbackは行わない。

初期既定は`none`とし、まずnative式を再現して比較する。bounded_least_squaresは対応を確認した後の明示設定とする。実装はSciPy least_squaresのtrf、線形loss、1初期値、max_nfev=1000から始める。比較fitはnative係数、最終fitは選定した比較fit係数を初期値にする。初期値のbounds違反、非有限残差、optimizerの不成功はfit失敗。探索中の不正領域を隠れた数値補正で通さない。solverの追加や多初期値は実測で必要になってから行う。

native候補を上書きせず、候補ID＋fit variantで区別する。別々のexpression/model/evaluation ID型は必須にしない。重複検出用の式・係数hashは必要時に共通関数で計算する。構造再現率の研究を実装するまでstructure_id基盤を作らない。

PySIPSの事後分布へ共通最小二乗を適用しない。点候補抽出とnative事後予測は別トラック。posterior対応時にだけその保存・推論を拡張する。

### 5.3 Finalと失敗

選定決定とfit方針を保存した後にFinalを読む。Finalの成績で別式を選び直さない。最終fitが失敗したら公開を止める。Finalを見て条件を調整した場合は新たな探索として扱い、同じFinalを独立確認と主張しない。

設定・入力・基盤障害は通常の例外でよい。探索の部分失敗は`allow_partial_engines=true`のときだけstatus/reasonを返して比較を継続し、欠落を要約へ表示する。全候補不適格なら失敗。初期から全クラッシュ回復・分散リトライ基盤を作らない。

statusはEngine単位でok/failed/timeoutに統一する。exportで一部候補を落としても、有効候補が残ればok。0候補ならfailed。runnerはWorker境界で失敗・timeoutをsummaryへ保存し、既定では親Runを例外終了させる。allow_partial_enginesがtrueなら正常結果だけで継続し、欠落Engine/seedを親要約へ表示する。timeoutでkillしたWorkerの途中出力は初期版では採用しない。

## 6. 四つのStageと最小成果物

| Stage | 一つの仕事 | 最低限の出力 |
| --- | --- | --- |
| prepare | 入力・固定分割・実行条件の確定 | train/selection/finalの数値表、`run.json`（解決設定・split・データ出自） |
| discover×engine×seed | 独立探索とexport照合 | `candidates.jsonl`、`engine_summary.json` |
| compare | 共通評価・適格性・1式の選定 | `leaderboard.csv`、`selection.json` |
| finalize | 固定構造の最終fit・Final評価・保存・報告 | `equation_model.zip`、`model_info.json`、`result_summary.json` |
| infer（別Task） | 採用bundleを新データに適用 | `predictions.csv`、要約。入力不正なら列/行を示す |

図・制約別詳細・予測CSVは必要な利用画面で追加する。正規化・reportのためだけのStageは作らない。ラベル・設定・結果の同じ情報を複数ファイルで独立管理しない。

bundleは最初は`equation.json`（AST・係数）、`schema.json`（列・単位・変換・範囲）、`metadata.json`（出自・Selection/Final評価・制約）、`manifest.json`（版とファイルhash）の4ファイルでよい。JSON schemaの生成基盤は不要。版・必要フィールド・hashと安全なZIP pathをロード時に確認する。

SDK非依存の`load_model(path).predict(frame)`を提供する。採用した単一式の予測に探索ライブラリ・重み・ClearMLを要求しない。欠損列・非有限値・式の未定義はエラー、学習範囲外の有限な予測は警告。行を消さない。

`run.json`に設定、データ/分割hash、seed、コード・依存版、任意のasset hashを一度記録し、後続へ参照する。初期必須診断はstatus/reason、入出力件数、native照合結果、wall時間のみ。GPU利用率、peak memory、大量ledger、全候補の画像、複数の監査IDは任意とする。

### 6.1 Stageの引数とファイル名

公開ローカル入口は`run_task(config: Mapping, *, run_dir: Path) -> RunResult`。初期は`task=symbolic_pipeline`で4Stageをローカル実行し、`task=symbolic_infer`でbundleと新表から予測する。YAML読込は既存coreの関数を使う。分散Stageは`task=symbolic_stage`と`run.stage`で同じ内部関数を呼ぶ。追加の汎用Job/Executorクラスは作らない。

| Stage | 明示的に受け取るもの | run_dir内の出力 |
| --- | --- | --- |
| prepare | config、入力表、split設定 | `prepare/train.npz`、`selection.npz`、holdout時のみ`final.npz`、`run.json` |
| discover | train.npz、解決設定、engine、seed、context | `discover/<engine>/<seed>/candidates.jsonl`、`engine_summary.json` |
| compare | train/selection、全探索結果、解決設定 | `compare/leaderboard.csv`、`selection.json` |
| finalize | selection.json、train/selection、任意のfinal、共通出自 | `finalize/equation_model.zip`、`model_info.json`、`result_summary.json` |

npzの中身はX/y/row_idsだけとし、dtypeはfloat64/float64/Unicode。object配列を使わず、ロードはallow_pickle=False。列定義とgroup/split情報はrun.jsonに一度保存する。discoverへFinalを含む表全体を渡さない。prepareで列・有限値・splitの品質検査は行ってよいが、Finalのモデル指標は計算しない。

selection.jsonはcandidate_id、fit_variant、**選定時の式dictそのもの**、選定規則・閾値、Selection指標を持つ。finalizeが全候補から再選択する必要をなくす。leaderboardはcandidate_id/engine/seed/fit_variant/rmse/mae/r2/n_nodes/n_parameters/eligible/reasonを基本列とする。出力不足・schema不一致は境界で一度だけ検査する。

result_summary.jsonはstatus、comparison_complete、missing_runs、selected_candidate_id、selection_metrics、final_metricsを持つ。exploratoryではfinal_metrics=nullとする。ファイル名とClearML Artifact keyを分け、`model_bundle`→equation_model.zip、`model_info`→model_info.json、`result_summary`→result_summary.jsonとしてmanifest.pyで宣言する。model_infoはbundle内metadataから作る表示用の写像であり、第二のモデル正本ではない。

RunResultは最終のbundle、info、要約、leaderboardを既存artifacts/tablesへ登録する。Stage間は渡されたローカル参照だけを読み、他Stageのフォルダ名を推測しない。remoteでの参照解決・転送はspdmlが担当する。run_dirは新規の空ディレクトリを使い、同じpathへの学習再実行は既定で拒否する。自動resumeは初期対象外。

### 6.2 最小の完全な設定例

以下は同梱ZIPを展開したrootをCWDとした設定。パッケージ本体は未実装なので、現時点で実行できるコマンドとはしない。実装者はこの設定のローカル縦断動作を最初の完成例にする。

```yaml
task: symbolic_pipeline
data:
  local_path: data/yacht/table.csv
  target_column: resistance
  feature_columns: [buoyancy_position, prismatic_coefficient, length_displacement_ratio, beam_draught_ratio, length_beam_ratio, froude]
  id_columns: [sample_id]
  units:
    buoyancy_position: "1"
    prismatic_coefficient: "1"
    length_displacement_ratio: "1"
    beam_draught_ratio: "1"
    length_beam_ratio: "1"
    froude: "1"
    resistance: "1"
split:
  method: fixed
  file: data/yacht/split.csv
  group_column: group_id
search:
  engines: [pysr, physo]
  operators: [add, sub, mul, div]
  seeds: [42]
  max_wall_seconds: 300
  max_export_candidates: 100
  allow_partial_engines: false
  engine_options:
    pysr: {}
    physo: {}
constraints:
  max_nodes: 30
  require_units: false
evaluation:
  mode: holdout
  coefficient_fit: none
  selection_policy: balanced
  relative_tolerance: 0.05
  absolute_tolerance: 0.0
```

既定値はoperators=[add,sub,mul,div]、seeds=[42]、300秒、最大100候補、max_nodes=30、units必須false、holdout/none/balanced/0.05/0.0とする。numeric validityとexport照合は常時必須。require_units=falseでも既知次元の違反を合格扱いにせず、未確認はunknownと表示する。複雑な制約を使う場合だけ専用spec_fileを追加する。

初期設定の優先順位は既定値→Task YAML→NEW RUNの明示値。品質presetやengine_suiteは必要になってから追加する。パラメータ名・型・説明はmanifest.pyに一度宣言し、config.pyはその正規化結果を検証する。共通設定の未知キーはエラー。native optionsもAdapterで検証し、同じ辞書を別の層で再検証しない。

設定の相対pathはローカルではCWD基準、ClearMLのdataset_file/split.fileは解決したDataset root基準。remoteでlocal_pathとの二重指定は拒否する。探索変数にはID/group/split列を入れない。unitsのない変数をPhySOへ渡す場合は、実行前に入力単位不足を明示する。

固定split.csvの列はsample_id/partition、partitionはtrain/selection/final。sample_idは入力側も一意・非空、重複/未知/欠落IDを拒否する。group_columnを指定した場合は全partition間のgroup非重複も検査する。exploratoryならfinal行を持つsplitを拒否し、二分割を明示させる。初期はfixed/groupの二方式を完成させ、time/CVは後続とする。

### 6.3 推論の最小動作

`load_model(bundle).predict(frame)`は保存schemaのcolumn名で並べ替え、入力行順のfloat64(n,)を返す。Frameの列位置に依存させない。入力単位はschemaで宣言した単位を前提とし、Frameから単位を推測しない。異なる単位を使う場合は利用者が明示変換する。

余剰列は許可し、不足列・非有限入力・出力の未定義は最初の該当列/行を示して失敗する。学習範囲外は有効な予測を返し、infer Taskの要約へ件数を出す。矩形範囲内だから未観測の組合せも安全とは保証しない。初期版は部分成功CSVやrow別status列を必須にしない。推論Taskの基本CSVはrow_index、任意ID、predictionとする。

## 7. ClearMLと既存基盤へ接続する順序

ローカル縦断動作が通ってから、既存の`PipelineDefinition`とManifestへsymbolicを追加する。新しいDomain登録システムを並立させない。

| 接続箇所 | 最小変更 |
| --- | --- |
| core/stagesと設定検証 | Manifestの許可Stageを使う。tabularの互換動作を維持 |
| spdml app/parameters/plan | Manifest・runner・plan builderを明示注入 |
| Artifact結線 | DomainStepPlanへ必要な入力参照だけ追加。SDK URLの生成はspdmlが担当 |
| Controller/status/reports | 結果Stageとbundle/infoの出力宣言を参照。表名から意味を推測しない |
| model resolver/inference draft | `selected`を解決し、成功DAGの所有Taskとhashへ固定 |
| adapter/model publication | 数式をscikit-learnと誤表示しない。bundleの登録・公開・experimentalの区分を明示 |
| bootstrap/環境 | symbolicを認識。事前学習用Python 3.12 Workerが必要になった時に分離 |

候補はTask Artifact、採用式だけをRegistryへ登録する。既存コードのpublishedは版固定と推論利用の状態であり、業務承認とは区別する。NEW RUN→親Pipelineの候補表→採用式→推論Draftの既存操作を維持する。独自Web UIや承認システムは作らない。

初期は既存の一つのStage templateでよい。RASR等の環境差が実際に必要になった時点で、Engine別template/queueをReleaseへ追加する。多環境Releaseと公開修復の仕組みを、最初のローカル実装の前提にしない。

## 8. 実装チケットと完了条件

| 順 | 実装範囲 | コーディングエージェントが示す完了証拠 |
| --- | --- | --- |
| 1 | 小さなAST、モデル保存・ロード、既知式fit | 自由係数だけをfitし、保存前後と列順変更後の予測が一致 |
| 2 | data、固定split、fake候補、共通評価・選定 | Finalを変更しても採用構造が変わらず、group非重複を確認 |
| 3 | PySR＋PhySOの実Adapter | 各1例のnative/export一致と、Yachtの共通候補比較 |
| 4 | ClearML接続 | NEW RUN→採用式→推論Draft。未実機確認ならその旨を記録 |
| 5 | Flash-ANSR＋TorchSISSO | 軽量事前学習と記述子選択。既存Evaluatorを変更せず接続 |
| 6 | ProGED、ParFam、RASR、PSE | 各役割の実測比較。失敗・未対応を区別 |
| 7 | PySIPS、PISR | posteriorを壊さない保存、正解式不要のPISR bridge |

各チケットは必要な変更、利用例、検証結果だけをまとめる。全10Engineの全組合せ試験を作らない。今回の文書はコード実装完了を意味しない。

## 9. 検証を複雑にしないための規則

| 検証 | 必要な内容 | 実行時期 |
| --- | --- | --- |
| 式とbundle | 定義域、固定値/自由係数、単位換算、保存後予測 | 通常のfast tests。少数のパラメトリックケースにまとめる |
| data/選定 | 固定split・group、Final非参照、同点ルール | 同上。小さなfixtureで検証 |
| Adapter | 各実EngineのnativeとASTの予測一致 | 対象Adapter/依存変更時。依存なしCIでは理由付きskip |
| 縦断動作 | prepare→比較→保存→新データ予測 | fakeでfast、実Engineは軽量integration |
| 外部データ比較 | Yacht、Airfoil、Concrete | ベンチマーク。ネットワーク・checkpoint・GPUを通常pytestに要求しない |

目安として`test_expression_model.py`、`test_data_selection.py`、`test_pipeline.py`、`test_adapters.py`の4ファイルから始める。ファイル数やテスト数を受入指標にしない。型・登録リスト・内部関数の実装を写すだけのテストは不要。実際の不具合や境界に対する回帰試験を追加する。

外部データで一定R²を全手法へ課すゲートや、短時間のランダム探索で特定の式文字列を回復するゲートは置かない。数値機能の正常性と科学的な性能比較を分ける。外部データのbaselineは学習meanと小さなridgeから始め、実測の合格精度は別途決める。

既存リポジトリへ実装する際は、親AGENTS.mdが要求するquality-fast、quality-pr、strict docs等を実行する。ここで「軽量」としたことを理由に既存の必須ゲートを省略しない。今回実行したのはデータ取得・分割・整合性と文書例の確認であり、探索EngineやClearML UI試験ではない。

## 10. 手法調査と優先10手法

### 10.1 選定結果と考え方

調査基準日は2026-10-25。優先度は今回の装置実測・制約・比較基盤への導入効果についての判断であり、実データで確認した精度順位ではない。10手法のうち7手法で探索原理の違いを確保し、指定されたRASR・Flash-ANSR・PISRで事前学習の設計差を比較する。

| 区分 | 選定手法 / Engineキー案 | 関数をどう求めるか | 比較で確認できること | 主な利用案 |
| --- | --- | --- | --- | --- |
| 汎用探索 | **PySR / `pysr`** | 式木の進化探索と係数最適化 | 自由探索の基準。知識や関数族を限定した方式との差 | 条件→エッチ量・均一性・モード係数 |
| 物理制約付き生成 | **PhySO / `physo`** | 強化学習による式生成を物理次元等で制御 | 単位・物理情報を探索時に与える効果 | 単位が明確な温度・流量・寸法の式同定 |
| 記述子選択 | **TorchSISSO / `torchsisso`** | 演算展開した記述子からscreeningと疎な項選択 | 多数の入力を少数の複合指標へ縮約できるか | ノズル幾何・レシピを説明する設計指標 |
| 文法誘導 | **ProGED / `proged`** | 確率的文法から候補を生成し、係数をfit | 専門家の関数形・機構仮説が探索に与える効果 | 許可する加算・乗算構造、機構項の比較 |
| ベイズ推定 | **PySIPS / `pysips`** | SMCで式の事後分布を近似 | 一つの式へ絞れるか、複数仮説が残るか | ノイズ・再現性ばらつきによる構造不確かさ |
| 連続最適化 | **ParFam / `parfam`** | パラメトリック関数族を使って式探索を連続最適化として解く | 離散的な式木探索と関数族を決めた最適化の違い | 有理関数等を含む関数族での簡潔なモデル |
| GPU並列列挙 | **PSE / `pse`** | PSRNで部分式の計算を共有し、多数の式をGPUで並列評価 | 進化探索・学習済み生成と、大量列挙の効率・探索範囲の差 | 少数の入力で式空間を広く調べる探索 |
| 事前学習① | **Flash-ANSR / `flash_ansr`** | 学習済みモデルで式を生成し定数調整 | 事前学習による短時間生成と、生成予算の効果 | 多数の指標・データ群への初期候補探索 |
| 事前学習② | **RASR / `rasr`** | 実測を意識した合成事前分布と事後学習を使う式生成 | 実測に近いノイズ・入力分布を学習する効果 | 不均一・ノイズを含む装置実測 |
| 事前学習③ | **PISR / `pisr`** | データと数式を対応付けた学習済み空間から候補を生成 | 物理式を意識した学習済み表現・検索を利用する効果 | 物理式の構造回復や物理量間の関係探索 |

既知式＋SciPyによる係数fitは10手法に共通する基準として別に置く。自由探索の改善幅を測るため、Arrhenius型、飽和応答、輸送等の仮説を利用者が明示して比較する。構造探索を行わないため10枠には数えない［R1］。

### 10.2 7つの探索方式の実装単位

| 手法 | Adapterの処理と取得する結果 | 対応制約・注意点 | 導入時の検証 |
| --- | --- | --- | --- |
| PySR | 共通specをnative設定へ変換、探索、候補集合と自由係数を取得、AST化 | 自由探索とテンプレート探索を別設定で管理。任意combineは可搬化可能な範囲に限定 | 演算意味、スケーリング復元、候補ごとのnative一致［S6,S7,R2］ |
| PhySO | 次元・固定/自由係数を設定し通常SRを実行、式木と係数を取得 | 単位整合と単調性・正値の全域保証は別。Class SRは後続契約 | protected演算、係数の次元、未知単位の拒否［S8］ |
| TorchSISSO | 記述子展開の深さ・項数・screening条件を固定、選択記述子と線形係数をASTへ展開 | 深さ・変数数で候補数が増大。相関記述子による選択変動を評価 | 単位設定、定数/係数、複数候補取得方法。Python/PyTorchへの適合を重視して選定［R3］ |
| ProGED | grammarを検証・hash化、静的回帰の候補生成と係数推定、候補をAST化 | grammarのhardな制限と生成確率のsoftな誘導を分ける。生成確率は物理的正しさの確率ではない | 静的回帰API、文法版、係数、候補export。ODE経路は初期対象外［R4］ |
| PySIPS | 尤度・事前分布・SMC設定を保存して探索、点候補と事後情報を分けて取得 | 事後分布へ共通最小二乗refitを適用しない。ノイズモデルと収束に依存 | 点候補export、事後重み/予測の取得と保存、推定診断［R5］ |
| ParFam | 関数族・次数・許可基本関数と大域最適化設定を固定、最適化後の式・係数を取得 | 自由探索と関数族が異なる。学習誘導DL-ParFamは別variantとして記録 | 元の式への復元、係数と固定指数、最適化失敗。内部optimizerの能力を制約保証と混同しない［R13］ |
| PSE | 演算集合・展開範囲・GPU予算を設定し、PSRNによる並列評価から式を取得 | 列挙する範囲とGPUメモリが制約。GPUを使うことと事前学習重みを使うことは別 | 列挙範囲、共有部分式、候補数、係数取得、native一致。PSEは手法全体、PSRNは中核モジュール［R14］ |

PhySOとProGEDは両方とも探索を制限するが、前者では物理次元、後者では専門家が与える関数形・構造規則を使う効果を分けて調べる。TorchSISSOをSISSO系の第一候補とするのは既存技術構成との接続を重視した判断であり、SISSO++より高精度と判定した結果ではない。

### 10.3 事前学習3手法を同時に採用する理由

| 手法 | 一次資料で確認した特徴 | 比較の位置付け | 確認範囲 |
| --- | --- | --- | --- |
| Flash-ANSR | ICML 2026論文、公開checkpoint、候補集合・定数調整・生成履歴のAPI | 接続しやすい事前学習型の基準。速度–候補数–式の簡潔さを比較 | 公式READMEとpyproject。実行未検証［R8］ |
| RASR | 2026-10-13プレプリント。合成事前分布を実測へ近づけ、強化学習で事後学習 | ノイズ・相関入力・構造的誤差を含む実測への適合性を比較 | 公式README、tutorial、inferenceクラス、依存定義を読んだ。実行未検証［R6］ |
| PISR | 2026年7月公開のコード・重み・検索索引。共通表現、flow、decoder等の構成 | 物理式を意識した学習済み表現・検索・生成の比較 | 配布ページとREADME。配布ZIP内部の実装・実行は未検証［R9］ |

3手法はすべて事前学習系だが、基準となる学習済み生成、実測分布への適応、物理式の表現・検索という違いがある。ただし手法を切り替えるだけでは学習データ・モデル規模・推論計算量等も変わるため、結果差を特定の学習要素だけの因果効果とは解釈しない。

### 10.4 調査した追加候補と保留理由

| 候補 | 求め方・役割 | 今回の10枠外とする理由／追加条件 |
| --- | --- | --- |
| SISSO++ | SISSO系のC++実装 | TorchSISSOと役割が重なる。APIや候補exportが不十分なら代替として検証［R7］ |
| TPSR | 事前学習モデルのデコードへMCTSを追加 | 3つの事前学習系の接続後に、追加探索の効果を検証する枠［R10］ |
| LLM-SR | 問題説明・科学知識から式のプログラム骨格を提案しfit・探索 | 有力な追加候補。初期10枠ではGPU列挙を優先し、生成コードの隔離とAST限定exportは後続設計［R11］ |
| Operon / pyoperon | C++のGPとPythonインターフェース | PySRと進化探索の視点が重なる。実装速度・資源効率比較向け［R15］ |
| AI Feynman | 対称性・分離可能性等による問題分解 | 分離できる物理関係の検証へ用途を限定して追加［R16］ |
| L2G-SR | 学習した構造評価器でLLM探索を誘導。2026年10月プレプリント | LLM-SRの接続後に検討。評価器スコアを真の構造正解判定には使わない［R12］ |

### 10.5 比較・係数fit・事後予測の分離

| トラック | 共通化する処理 | 保持する違い |
| --- | --- | --- |
| native単一式 | 同じデータ・Runtimeで誤差・式サイズ・制約を評価 | 各手法が学習した係数を維持。`coefficient_fit=none` |
| 共通refit単一式 | 5.2節の共通train fit、Selection評価 | native候補を保持し、候補ID＋fit variantで区別。対応不能な候補は明示 |
| native事後予測 | 同じ評価データで被覆率・区間幅、取得可能ならNLPD/CRPS | PySIPSの尤度・事後情報を保持。最小二乗で置き換えない |
| 知識付与 | 単位・grammar・テンプレート・問題説明の有無を固定して比較 | 与えた知識量と内容のhashを保存 |

PySIPSから抽出した構造を共通refitすることは可能だが、その結果は「抽出構造の点推定」であり、元の事後分布とは区別する。NLPDは正規化された予測密度が得られる場合だけ計算する。LLMや事前学習モデルの生成確率は、物理的正しさの確率として使わない。

初期bundleは単一式を対象とし、posteriorやClass SRの共通構造・別係数は対応時にschemaを拡張する。PySIPSの点候補を取得できても、native事後予測が未実装なら完全対応とは記載しない。単一式推論が探索依存なしで動く保証を、そのままposterior推論へ拡大しない。

### 10.6 導入順と実証の問い

| 段階 | 対象 | 完了時に確認すること |
| --- | --- | --- |
| A | PySR、PhySO、既知式fit | 初期の共通式・評価・ClearML導線 |
| B | TorchSISSO、Flash-ANSR | 記述子選択と事前学習生成の接続。式数・資源・exportの共通記録 |
| C | ProGED、ParFam、RASR | 文法・連続最適化・新しい学習済み生成の比較 |
| D | PySIPS、PSE、PISR | 事後出力、GPU列挙、配布コードbridgeの追加契約 |

PISRのsource確認と重みの整合検証、RASRの環境検証は早期に着手し、難所を後まで残さない。上表は完了の依存順であり、研究実証を後回しにする優先順位ではない。全10手法が常に動くsuiteを初期の既定にはしない。

装置実測ではgroup単位でデータ量を変え、誤差、制約適合率、複雑度、係数変動、探索時間を比較する。真の式が不明な実測で構造正解率を作らない。構造回復は既知関数の合成データで別評価する。学習範囲外の実測がなければ外挿精度を主張しない。

### 10.7 調査の一次資料

確認日は2026-10-25。論文・READMEの主張と本書の導入提案を区別する。ソース・重み・学習データの利用条件は対象版で別々に確認する。

| ID | 一次資料 | 主な確認事項 |
| --- | --- | --- |
| R1 | [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html) | 境界付き係数fit |
| R2 | [PySR](https://github.com/astroautomata/PySR) | 汎用SR。単位・テンプレートはS6/S7も参照 |
| R3 | [TorchSISSO](https://github.com/PaulsonLab/TorchSISSO) / [論文](https://arxiv.org/abs/2410.01752) | 展開・項数・単位・PyTorch実装 |
| R4 | [ProGED](https://github.com/brencej/ProGED) / [論文](https://arxiv.org/abs/2012.00428) | PCFGと係数推定 |
| R5 | [NASA PySIPS](https://github.com/nasa/pysips) | SMCと事後予測 |
| R6 | [RASR](https://github.com/automl/rasr) / [論文](https://arxiv.org/abs/2610.17994) / [tutorial](https://github.com/automl/rasr/blob/main/notebooks/tutorial.ipynb) / [inference実装](https://github.com/automl/rasr/blob/main/src/rasr/inference/rasr.py) | 学習・生成・入力条件・native API |
| R7 | [SISSO++ JOSS論文](https://joss.theoj.org/papers/10.21105/joss.03960) | SISSO系代替 |
| R8 | [Flash-ANSR](https://github.com/psaegert/flash-ansr) / [ICML 2026論文](https://proceedings.mlr.press/v306/saegert26a.html) / [pyproject](https://github.com/psaegert/flash-ansr/blob/main/pyproject.toml) | 候補・生成履歴・依存 |
| R9 | [PISR配布資料](https://zenodo.org/records/21618861) / [配布README](https://zenodo.org/records/21618861/files/README.md) | コード・重み・索引・実行例。学習コーパス全体は要問合せ |
| R10 | [TPSR](https://github.com/deep-symbolic-mathematics/tpsr) | TransformerとMCTS |
| R11 | [LLM-SR](https://github.com/deep-symbolic-mathematics/LLM-SR) / [論文](https://arxiv.org/abs/2404.18400) | 科学知識による骨格探索 |
| R12 | [L2G-SR論文](https://arxiv.org/abs/2610.20685) | 構造評価器の探索誘導 |
| R13 | [ParFam](https://github.com/Philipp238/parfam) / [論文](https://arxiv.org/abs/2310.05537) | 連続最適化・DL-ParFam |
| R14 | [PSE/PSRN](https://github.com/intell-sci-comput/PSE) / [論文](https://arxiv.org/html/2407.04405v4) | GPU並列列挙 |
| R15 | [Operon](https://github.com/heal-research/operon) / [pyoperon](https://github.com/heal-research/pyoperon) | C++ GPとPython API |
| R16 | [AI Feynman](https://github.com/SJ001/AI-Feynman) | 物理的な分解構造 |

## 11. 事前学習系を扱う基盤とAdapterの詳細設計

### 11.1 共通化する範囲

事前学習モデルは、重みを使って条件表から数式を提案する**探索Engine**として扱う。採用した数式で新データを予測する**式モデル**とは区別する。通常のdiscoverでニューラル重みの更新は行わない。定数の数値最適化は別途許可する。

共通化するのは重み参照、入力適合の記録、予算・時間、export検証、出自であり、3手法のtokenizerやdecoderを一つの巨大な共通モデルクラスにしない。既存`DiscoveryEngine.discover()`を維持し、各Adapter内部の処理を以下へ分ける。

| 処理 | 所有者 | 入出力・責務 |
| --- | --- | --- |
| assetの登録・取得 | spdml / ローカル起動層 | 版固定の外部重みを配置し、ローカルpathと検証情報を渡す |
| assetの完全性検査 | 軽量な`assets.py` | hash、必要ファイル、サイズ、互換版を確認。SDK・自動ダウンロードなし |
| 入力準備 | 各Adapter | trainの型・サイズ・列順・内部変換を検証して記録 |
| モデルロード | 各Adapter | 正式なロード経路でcheckpoint/tokenizer/indexをロード |
| 候補生成・native定数調整 | 各Adapter | trainだけを使用。生成上限・seed・メモリ・時間を記録 |
| export・照合 | 各Adapter＋共通Runtime | 正確な係数と元座標のASTを生成しnative照合 |
| 共通評価・選定 | 既存compare | native scoreを使わず共通Selectionで再評価 |
| 最終保存・推論 | 既存finalize/infer | 通常の単一式bundleを生成。重みを推論に要求しない |

2章の構成へ追加するモジュールは、共通の`assets.py`と`engines/flash_ansr.py`、`engines/rasr.py`、`engines/pisr.py`を基本とする。各ライブラリの依存・コード量が大きい場合だけ`engines/<name>/`へ分割する。未対応のEngineファイルを空のstubとして公開しない。

### 11.2 asset契約と版固定

モデル名や外部URLだけを保存して再現可能としない。JSONの`asset_manifest`と解決済みローカルdirectoryを使う。参照用と解決済み用の二つの公開クラスを増やさない。

| フィールド | 内容（初期はsource/revision、ファイルhash、対応Engineを必須とし、その他は既存run情報を参照または任意） |
| --- | --- |
| `asset_id`, `engine`, `variant` | 不変asset版、対応Engine、checkpoint系列 |
| `source`, `source_revision` | 配布元、固定commit/revisionまたは固定record版。`main/latest`だけは禁止 |
| `files[]` | 相対path、役割、byte数、SHA-256。checkpointだけでなくconfig・tokenizer・索引metadataも対象 |
| `code_revision`, `adapter_version` | 推論実装と変換コードの版 |
| `environment_lock_hash` | Python/PyTorch/CUDA/SimpliPy等の環境lockのhash |
| `capability_profile` | 対応列数・点数・演算・数値表現・正規化。根拠と確認状態を含む |
| `training_data_card` | 学習データの種類・規模・ノイズ・重複検査の分かる範囲。未知はunknown |
| `license_refs` | コード・重み・データそれぞれの利用条件参照 |

spdml層は必要に応じてClearML Dataset等の不変データ資産としてassetを取得し、探索Taskへローカル参照を渡す。候補生成用の重み資産と、採用式のOutputModelを同じRegistryモデルとして混同しない。重みは各候補bundleへ複製せず、provenanceからasset hashへ参照する。

まず版固定の事前配置directoryを使い、asset hashを検証する。共有cacheの自動取得・ロックは複数Workerで実際に必要になってから追加する。Run実行時の外部ダウンロードを既定で行わず、事前配置したassetからオフラインでも起動可能にする。pickle依存のcheckpointは対象版の信頼できるロード経路を確認し、任意のユーザーpickleを共通Runtimeへ渡さない。

### 11.3 入力サイズ・標準化・生成予算の共通規則

初回検証で使用するasset候補は以下とする。モデル名は固定revisionとファイルhashで解決してから使う。表の上限・規模は参照資料の対象版の情報であり、対応版を変更したら再検証する。

| 手法 | 初回のasset候補 | 学習データ・表現の分かる範囲 | 未確認事項と実装判断 |
| --- | --- | --- | --- |
| Flash-ANSR | `psaegert/flash-ansr-v25.0-T8-20M`を基準候補。軽量試験は同系列3M版を別variantとして使用 | 合成式を用いた学習と簡約処理。checkpointにひも付くgrammar/configを取得する | 点数・変数数・演算の上限をmodel configから確認。別サイズを同じモデルとして集計しない［R8］ |
| RASR | tutorialの`davidotte/RASR-94M-L`を基準候補 | 表形式モデル由来の入力事前分布、条件付き定数、異分散・構造的ノイズを含む合成学習 | 論文の11特徴・2048行を初期の保守的なprofile上限として扱い、nativeの挙動を別途検証。自動特徴削減はしない［R6］ |
| PISR | 配布record v1の`manifold_v13_ms80.pt`、`flow_v13.pt`、`dec7_v13.pt`。検索時は`zf_v13_index.npy`、`zf_v13_meta.jsonl`、`nbr_v13.npy`を対応付ける | 配布READMEでは33.6M式の学習コーパス、400k式の検索索引と記載。学習コーパス本体は配布対象外 | 入力列数・点数・定数処理・verifier要否はZIPのsource/config確認までunknown。未知の上限を架空の値で埋めない［R9］ |

同一学習コーパスで訓練された3モデルではない。比較表にはtraining_data_cardの公開範囲・不明点を併記し、既知式ベンチマークでは学習データ・検索索引との重複を確認できた範囲を記録する。

| 論点 | 実装規則 |
| --- | --- |
| 点数上限 | 上限を超えた場合は既定でエラー。明示した場合だけtrain内からgroupを考慮して固定抽出し、行IDを保存 |
| 特徴数上限 | 勝手に先頭列へ切り詰めない。上流の明示した列選定または全Engine共通のtrain内選定が必要 |
| 異なる利用点数 | 各Engineの実効train行数・生成用support行数・係数fit行数を区別。制限が違うRunを完全同条件と表示しない |
| dtype | nativeのfloat32等を記録。export照合の許容差を事前固定し、通すために事後変更しない |
| 定数ターゲット・ゼロ分散列 | 共通prepareで検出。不要列の明示除外またはベースライン扱い。内部でゼロ除算させない |
| 標準化 | ライブラリ自身が行う変換を追跡。共通側で二重標準化しない。統計量はtrain由来のみ |
| 候補生成 | 生成数、batch、再試行、token長、temperature等は対応するoptionsだけを明示。共通の一つのtemperatureを無理に全Engineへ適用しない |
| 定数調整 | native定数調整は探索時間に含める。共通train refitと最終fitは別時間・別ID |
| 制約 | 重みのtoken集合変更やdecoder maskは対応確認済みの場合だけ。非対応条件はpost検査または事前拒否 |

例えばnativeが`z=(x-mu_x)/sigma_x`、`t=(y-mu_y)/sigma_y`で式`g(z)`を学習した場合、保存関数は`y=mu_y+sigma_y*g((x-mu_x)/sigma_x)`とする。mu/sigmaは固定値で、自由係数へ変えない。型、単位、列順も一緒に保存する。候補の表示文字列に丸めた係数をAST生成へ使わない。

最初は単一のCPU/GPU device、明示したCPU worker数から始める。CPU定数fitのpoolとGPU生成が競合しないよう、OMP/BLAS thread・refiner workerを制限する。OOM時のbatch縮小は事前定義した系列だけを許し、試行と時間を記録する。候補数や使用データを無言で減らして成功にしない。

### 11.4 Flash-ANSR Adapter

**確認済みの接続点**：公式READMEに`FlashANSR.load`、`SoftmaxSamplingConfig`、`fit`、`FitResult.candidates`、`ledger`、候補ごとの予測、生成/調整時間が示されている。Python >=3.12を要求する。checkpoint系列には複数サイズがある［R8］。

実装手順は以下のとおり。ここからは基盤側の設計であり、完了した実装ではない。

1. manifestで固定したローカルmodel directoryを解決し、config・重み・依存の互換性を検査する。モデルIDの自動最新版取得を行わない。
2. 学習済みgrammarの対応変数・演算子・長さをcapability profileへ反映する。profileが未確認の設定を対応済みと表示しない。
3. 対応版のsampling configへ`draws`等を渡し、`compute`へdevice・CPU workersを明示する。nativeの内部rankingは診断専用にする。
4. Search Trainだけでfitする。候補集合から構造と丸め前の定数を取り出す。ledgerを使って生成数・重複・invalid・fit失敗を集約する。
5. token/式構造とconstantsからASTを構築する。整形式のinfixだけを取得できる場合は許可文法parserで扱い、任意evalはしない。
6. resultの候補予測とASTを候補単位で照合する。最良候補だけのpredictでは全候補の変換確認にならない。
7. 共通のtrain側切詰め規則で上限を適用し、candidates.jsonlとengine_summary.jsonへ保存する。

raw ledger全体は件数が大きければ任意Artifactとし、必須記録は件数・失敗理由に抑える。ライブラリ固有のpkl保存は共通bundleの正本にしない。Flash-ANSR→PySRのhybridは将来の別Engine variantとして扱い、単体Flash-ANSRの計算時間や成績へ混ぜない。

### 11.5 RASR Adapter

**確認済みの接続点**：公式tutorialとinference実装では、`RASR`、ローカルdirectoryを受け付ける`model_path`、`fit/predict`、`results_`と`pareto_front_`、入力・出力の標準化情報を確認した。環境はPython 3.12/3.13。公開論文の評価上限は11特徴・2048行であり、すべての将来checkpointの普遍的上限ではない［R6］。

実装手順：

1. 公式source commit・submodule版・model snapshotを固定する。現行sourceの`src.rasr...`というimport構成は互換bridge内へ閉じ込め、共通パッケージへ広げない。
2. ローカルasset directoryを`model_path`に渡し、外部snapshot取得へfallbackしないことを起動試験で確認する。
3. `num_candidates`、`decode_batch_size`、`n_restarts`、`refiner_workers`、`parsimony`等を対応版で検証して設定する。未確認のseedパラメータを仮定せず、native対応と乱数状態の設定範囲を記録する。
4. fitへ共通Selection/Finalを渡さない。native APIがvalidationを受け付けても、必要ならtrain内の事前固定splitだけを使用する。
5. nativeのresults集合から共通評価用候補を取得し、native Paretoを診断として保持する。native Paretoだけを返す場合は、その切詰め規則を記録する。
6. tutorialにあるcandidate.refinerによる標準化空間の予測と、入力・出力変換を合わせて候補ごとのnative予測を得る。最良式のpredictと候補indexの対応を混同しない。
7. refinerの構造・精度を保った係数と変換統計をASTへ移す。表示用の低精度`get_expression`を保存式に使わない。private属性の利用が避けられない場合はbridgeに限定し、そのcommit専用テストを置く。
8. poolをcloseし、GPU/CPU資源を解放して結果をatomicに確定する。

source確認と実行確認は分ける。CUDA・Triton等の依存を持つ環境を既存Python 3.11 Workerへ無理に同居させず、事前学習用のPython 3.12 Workerを用意する。nativeの標準化統計が0に近い場合や、ASTで表せない演算が含まれる場合は、対応失敗を明示する。

### 11.6 PISR Adapter

**確認済みの配布構成**：READMEには共通の数式/データencoder、flow-matching generator、検索、conditioned decoderと推論経路が示され、manifold/flow/decoderの重み、検索索引とmetadata、補助ファイルが配布されている。コードZIP内部は未確認であり、汎用的な`fit(X,y)`の存在や候補APIを仮定しない［R9］。

実装は次の順で進める。配布READMEのbenchmark実行コマンドを、そのまま業務探索として呼ぶ実装にはしない。

1. **source spike**：ZIPを展開して推論入口・config・tokenizer・候補構造・定数調整・検索時のデータ参照を確認する。公式のbenchmark再現と、任意X/yへの推論を別々に検証する。
2. **asset manifest**：少なくともmanifold、flow、decoderを個別hashで管理する。検索を有効にする設定ではindex・metadata・隣接情報を対応した一組として固定する。verifierの要否はconfigとsourceで確定する。
3. **bridge**：基盤側に`load_assets`、`generate_candidates`、`export_candidate`相当の小さな関数を作る。これらは提案する内部関数名であり、PISR公式API名ではない。配布コードを必要最小限で呼び出し、修正差分と元版を記録する。
4. **任意データ入力**：trainのX/yと列対応だけから入力を構築する。benchmark taskのground-truth lawや正解ラベル用の式を、生成・候補選定・係数調整へ渡さない。正解なしで実行できなければAdapter受入を止める。
5. **検索の出自**：検索索引に含まれる式とバージョンをassetに含める。検索候補IDを追跡し、既知式benchmarkでは式の索引混入を明示する。索引の近傍数などの実options名はsource確認後に専用schemaへ登録する。
6. **生成・定数調整**：decoderから丸め前の構造・係数を取得し、調整の有無と使用データを確認する。nativeが候補1件だけを公開する場合は`max_native_candidates=1`と宣言する。複数候補取得APIを捏造しない。
7. **export**：nativeの正規化と数値実行に一致するASTへ変換し、候補単位で照合する。native予測を取得できない場合も未検証候補を合格にしない。
8. **昇格**：任意実測データでの実行、正解式への非依存、asset再現性、AST照合を満たしてexperimental対応とする。未解決項目を残した状態では研究prototypeと明記する。

配布者の性能主張は再現済み性能として扱わない。初期には重みの再学習を要求せず、公開推論資産の有用性を評価する。学習コーパス全体が入手できない場合は再学習の再現性と推論の再現性を分けて記録する。

### 11.7 共通APIの追加と設定例

`DiscoveryRequest`の外側で解決したassetsを、3章のDiscoveryContext.assets_dirで渡す。辞書optionsにSDK objectや秘密情報を入れない。Engine固有処理へ過剰な共通継承クラスを要求しない。以下は3章と同じ入口であり、事前学習専用の第二APIではない。

```python
@dataclass(frozen=True)
class DiscoveryContext:
    assets_dir: Path | None
    work_dir: Path
    device: str

# 3章と共通の入口。native APIではない。
class DiscoveryEngine(Protocol):
    def capabilities(self) -> dict: ...
    def discover(self, request: DiscoveryRequest,
                 context: DiscoveryContext) -> DiscoveryResult: ...
```

未学習型Engineではassets_dirをNoneとする。capabilityは軽量な静的情報とasset profileで事前確認し、実Workerで重みとnative依存をロードして再確認する。ControllerがCUDA依存をimportする構成を避ける。

```yaml
search:
  engines: [rasr, flash_ansr, pisr]
  seeds: [42, 43, 44]
  max_wall_seconds: 1200
  max_export_candidates: 200
  engine_options:
    rasr:
      num_candidates: 1024
      decode_batch_size: 16
      n_restarts: 4
      refiner_workers: 2
    flash_ansr:
      draws: 1024
      workers: 2
    pisr: {}  # native optionsは配布source確認後に宣言
model_assets:
  rasr:
    manifest_file: assets/rasr_manifest.json
  flash_ansr:
    manifest_file: assets/flash_ansr_manifest.json
  pisr:
    manifest_file: assets/pisr_manifest.json
evaluation:
  coefficient_fit: none
```

上例は6.2節の完全な設定へ適用する差分であり、単独の実行設定ではない。manifest_fileはローカルまたはDatasetから解決したpathで、モデル本体の自動取得を意味しない。`pisr: {}`は受入済みAdapterの既定optionsを使う意味とし、未対応状態で実行すれば事前エラーにする。初期はengine_suite等の別の選択方法を作らずsearch.enginesへ統一する。

native比較はnone、共通refit比較は別Runでbounded_least_squaresを指定する。native定数fitと共通fitの二重の時間を記録する。全checkpointを同時ロードせず、engine×seedの探索Taskで独立起動する。model_assetsセクションはsymbolic/config.pyで検証し、公開値はManifestへ宣言する。

### 11.8 ClearMLの実行環境・成果物

| 項目 | 実装する内容 |
| --- | --- |
| Worker | まず事前学習専用Python 3.12環境。依存衝突時はRASR/Flash/PISRごとのWorker imageへ分離 |
| Plan | engineごとにQueue・Stage template・環境lockを選べる宣言を追加。現在の全Stage同一template/queue固定を限定改修 |
| Release | 複数templateのtask IDとimage digestをRelease manifestに固定。既存tabularの単一template読込は互換維持 |
| Asset取得 | spdmlが固定版を取得し、discoverへローカル参照を渡す。Stage引数に環境依存のWorker一時pathを永続保存しない |
| 成果物 | asset参照・入力変換・生成件数・export結果はengine_summaryへ集約。raw ledgerや分離した詳細レポートは必要時だけ追加 |
| scalar/表 | 生成/有効/重複/fit失敗/export成功数、モデルロード/生成/native fit/export時間、peak memory |
| 採用式 | 通常のmodel_bundleをOutputModelとして公開。重みのasset ID・hashをprovenanceに追加 |

コールド時間（cache検証・モデルロードを含む）とウォーム時間（ロード済みの生成・定数調整等）を分ける。既存のmax_wall_secondsはdiscoverプロセスのロード・生成・exportを含め、Queue待ち・環境構築・事前asset取得を除く。ロード時間は隠さず記録する。モデルロードが長い手法だけ計測外にする比較はしない。

### 11.9 検証・受入条件

| ID | 確認項目 | 合格条件 |
| --- | --- | --- |
| PT-01 | asset再現性 | 同じmanifestで同じファイルを解決。1byte破損・索引metadata不一致を拒否 |
| PT-02 | オフライン起動 | 事前配置後は外部サービスへ接続せず候補生成可能 |
| PT-03 | データ境界 | Selection/Finalラベル・benchmark正解式を生成処理へ渡さない |
| PT-04 | 入力適合 | 点数/特徴数超過・ゼロ分散・抽出時の実効行数を明示。無言の列落ちなし |
| PT-05 | 変換 | 標準化・出力scale・負値・大きな動的範囲でnativeとASTが許容差内 |
| PT-06 | 候補と係数 | 全export候補で照合。表示の丸め値やnative順位を共通正本にしない |
| PT-07 | 予算・資源 | OOM/timeoutで理由とpartial条件を記録。poolやGPU資源を解放 |
| PT-08 | seedと再実行 | 乱数設定・checkpoint・ハードウェアを固定して変動を測る。GPU完全決定性は未確認なら保証しない |
| PT-09 | 式の可搬性 | 採用ASTの予測は3つの事前学習ライブラリ・重みなしで動く |
| PT-10 | 実測への有用性 | 既知式/PySRと同じ分割で、誤差・制約・式サイズ・時間・失敗率を評価。論文の再掲だけで完了にしない |

初期の事前学習対応は「公開重みを使った候補生成」まで。社内データへのfine-tuningは別Taskとし、入力がparent asset＋train Dataset、出力が新asset版＋学習履歴となるよう後続設計する。同じRun中にモデル重みを更新して、固定checkpointでの比較と混ぜない。

## 12. 既存コードの参照資料

確認日は2026-10-25。リポジトリの記述は上記commitを基準とし、外部ライブラリの機能は以下の一次資料で確認した。外部ライブラリの対象版は実装時にlockし、docsの版だけを実行互換性の根拠にしない。

| ID | 一次資料 | 本仕様で確認した内容 |
| --- | --- | --- |
| S1 | [core/contracts.py](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/pkgs/core/src/ml_platform_core/contracts.py) / [result.py](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/pkgs/core/src/ml_platform_core/result.py) | 既存のManifest・DomainStepPlan・RunResult |
| S2 | [tabular/manifest.py](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/pkgs/tabular/src/ml_platform_tabular/manifest.py) / [domain_plan.py](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/pkgs/tabular/src/ml_platform_tabular/domain_plan.py) | 公開入力、split比率、既存DomainのStage契約 |
| S3 | [pipeline_plan.py](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/pkgs/spdml_layer/src/ml_platform_spdml/pipeline_plan.py) / [pipeline_steps.py](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/pkgs/spdml_layer/src/ml_platform_spdml/pipeline_steps.py) / [pipeline_controller.py](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/pkgs/spdml_layer/src/ml_platform_spdml/pipeline_controller.py) | tabular固定の計画、Artifact結線、結果監視 |
| S4 | [adapter.py](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/pkgs/spdml_layer/src/ml_platform_spdml/adapter.py) / [結果ガイド](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/docs/ml_platform_mkdocs/docs/results.md) | publishedモデル、Release検証、Registry、推論Draftの導線 |
| S5 | [AGENTS.md](https://github.com/dkawa2523/ml_platform/blob/91aa29a235527b9ecd6fc7f6d17101beb0cfe9a0/AGENTS.md) | 責務境界、品質ゲート、UI未確認時の扱い |
| S6 | [PySR: Physics and units](https://pysr.ai/v2.7.0/examples/physics) | 単位入力、次元違反ペナルティ、無次元係数指定 |
| S7 | [PySR: Expression specifications](https://pysr.ai/v2.7.0/examples/expression-specifications) | 既知外形のテンプレート、任意combineの通常export上の制約 |
| S8 | [PhySO: Features and Options](https://physo.readthedocs.io/en/latest/r_features.html) / [公式リポジトリ](https://github.com/WassimTenachi/PhySO) | 単位prior、固定/自由係数、式操作、通常SRとClass SRの区別 |
| S9 | [ClearML: Models](https://www.clear.ml/docs/latest/docs/fundamentals/models/) / [OutputModel](https://clear.ml/docs/latest/docs/references/sdk/model_outputmodel/) | ArtifactとModelの区別、手動登録、モデルmetadata |
| S10 | [ClearML: Logger](https://clear.ml/docs/latest/docs/references/sdk/logger/) | 表、画像、Plotly等の標準報告方法 |

