# Symbolic package coding handoff

この一式は、関数同定パッケージを実装するコーディングエージェント向けの設計・作業規則・実行可能な検証データである。探索パッケージ本体や10Engineを実装済みとはしていない。

## 読む順序

1. `AGENTS.md`：汎用的な開発ルール。既存リポジトリへ適用する際は親のAGENTS.mdと統合する。
2. `ml_platform_symbolic_spec_reviewed.md`：1–9章で最小実装を作る。10–11章は対象Adapterを実装するときに読む。
3. `VALIDATION_DATASETS.md`：外部3データの用途・列・分割・単位・出典。

仕様はv0.5。`examples/yacht.yaml`は最初のローカル縦断動作の設定、`examples/pretrained_overrides.yaml`は事前学習3手法の差分設定である。仕様のYAML例から生成したもの。本体未実装のため現時点で学習を実行する設定ではない。

## 最初の作業

- 既存のcore/tabular/spdmlを確認し、数式の保存・ロードと小さな既知式fitから開始する。
- fake候補で分割→評価→選定→推論を一周させる。
- PySR/PhySOの実AdapterでYachtの固定分割を使う。
- その後にClearML接続と事前学習系を追加する。

## データ

`data/`にはUCIのYacht/Airfoil/Concreteの公式ZIP、準備済みtable.csv、split.csv、metadataを含む。取得・固定分割の再生成スクリプトは` scripts/prepare_validation_data.py`。

```bash
python -m pip install pandas xlrd
python scripts/prepare_validation_data.py --out data --offline
```

pandas/xlrdはConcreteの.xls読込に使うデータ準備依存。YachtとAirfoilだけならstdlibで実行できる。列名変更・派生group・固定分割を追加している。元データの出典とCC-BY-4.0の表示はVALIDATION_DATASETS.mdとmetadataを参照。

## 確認したこと

3つの公式ZIPの取得、行数/列数/有限値、派生group、固定split、train/Selectionの平均予測baseline、オフライン再生成を確認した。Finalのモデル指標はデータ準備では計算しない。各Engineの探索・事前学習重みのロード・ClearML UI・現行リポジトリ品質ゲートは、この文書作成では実行していない。

既存root AGENTS.mdの上書き、リポジトリへの自動配置、commit/push、公開はこの一式に含めない。
