# 検証データセットと実行手順

確認・取得日：2026-10-25。探索EngineやClearMLの実装・性能検証は未実施。以下は実際に公式配布ZIPを取得し、数値表・固定分割を生成して確認したスナップショットである。

## 1. 最初に使う外部データ

小さく、数値入力のみで、装置解析に近い「設計・条件→観測値」を持つ3件を採用する。データセット名だけでなく、列、group、分割、用途を固定する。半導体装置の精度を代替評価するデータではなく、解析基盤と探索方式の実証に使う。

| データ | 入力→目的変数 | 取得後の規模 | 主な検証用途 |
| --- | --- | --- | --- |
| Yacht Hydrodynamics | 5つの形状指標＋Froude数→排水重量当たりの剰余抵抗 | 308行、6入力、22形状group | 小さな数値E2E、設計条件の未見group、疎な指標、事前学習との比較 |
| Airfoil Self-Noise | 周波数・迎角・翼弦長・流速・変位厚さ→音圧レベル | 1503行、5入力、106派生条件group | 条件掃引のgroup分割、非線形応答、式export・標準化 |
| Concrete Compressive Strength | 7配合量＋材齢→圧縮強度 | 1030行、8入力、428配合group | 少数の独立配合からの回帰、時間効果、相関入力、再現性ばらつき |

公式の行数・列・単位と照合した。Yachtのgroupは先頭5形状変数、Airfoilは周波数以外の4変数、Concreteは材齢以外の7配合変数の厳密一致から作った。**これらは元データに付与されたrun IDではなく、今回の評価用に定義した派生group**である。Airfoilの106 groupやConcreteの428 groupを独立した実験run数と断定しない。

## 2. ファイル構成と再現コマンド

```text
data/
  yacht/       # airfoil/、concrete/も同じ構造
    source.zip
    source.sha256
    table.csv
    split.csv
    metadata.json
scripts/prepare_validation_data.py
```

ZIPを展開したディレクトリで実行する。

```bash
# 添付snapshotからオフライン再生成。Concreteのxls読込だけpandas/xlrdが必要
python -m pip install pandas xlrd
python scripts/prepare_validation_data.py --out data --offline

# source.zipがない新規ディレクトリへ公式データを取得して生成
python scripts/prepare_validation_data.py --out downloaded_data

# stdlibだけでYachtを取得・準備する
python scripts/prepare_validation_data.py --dataset yacht --out yacht_only
```

スクリプトはダウンロード、数値読込、列名付与、派生group、固定split、metadataの生成だけを行う。探索・ClearML登録・モデル評価は実装しない。Concreteは公式の.xlsのためpandas/xlrdを明示した。データ準備専用依存であり、推論パッケージの必須依存へ加えない。

同じ出力先で再実行するとsource.zipを再利用し、保存checksumと照合する。最初の取得時に記録するhashは今回のsnapshotの識別であり、配布者が署名した真正性の証明ではない。異なるseedで再分割するとsplit.csvが変わるため、比較を始めた後に上書きしない。

## 3. 列定義と注意点

| データ | `feature_columns` | `target_column` | 単位 |
| --- | --- | --- | --- |
| Yacht | buoyancy_position, prismatic_coefficient, length_displacement_ratio, beam_draught_ratio, length_beam_ratio, froude | resistance | 全列が無次元。物理的な名称は公式説明を参照 |
| Airfoil | frequency, attack_angle, chord, velocity, displacement_thickness | sound_level | Hz, deg, m, m/s, m → dB |
| Concrete | cement, slag, fly_ash, water, superplasticizer, coarse_aggregate, fine_aggregate, age | strength | 最初の7列kg/m³、ageはday、strengthはMPa |

table.csvにはsample_idとgroup_idも含む。これらは予測入力にしない。型・行順・浮動小数値を保ち、標準化は行わない。Concreteには完全一致行が25件あったが、黙って除外せず同じ配合groupへ保持した。重複除外を試す場合は別Dataset版にする。

AirfoilのdBは対数的な測定表現であり、圧力Paと同じ次元チェックへ流さない。初期は数値回帰・exportの比較に使い、物理次元制約付きPhySOの必須ベンチマークにはしない。数値的に無次元化した入力で実行する場合は、物理次元の検証と別の仮定として明示する。

Concreteの材齢と強度の関係に、データだけから全域単調性を保証しない。Yachtの正値やその他の応答制約も、要求を設定した場合に指定領域で検査する。実測を真の閉形式の正解と呼ばない。

## 4. 固定分割

seed=42でgroup一覧を安定的に並べてshuffleし、最初のceil(0.2×G)をFinal、残りのceil(0.2×残group数)をSelection、残りをtrainとした。比率はgroupに対して適用し、行数を無理に64/16/20へ揃えない。

| データ | Train 行/group | Selection 行/group | Final 行/group |
| --- | --- | --- | --- |
| Yacht | 182 / 13 | 56 / 4 | 70 / 5 |
| Airfoil | 937 / 67 | 246 / 17 | 320 / 22 |
| Concrete | 652 / 273 | 149 / 69 | 229 / 86 |

split.csvはsample_id/partitionの二列。基盤側は明示された列名で読み、全sample_idが一度だけ現れること、未知IDがないこと、groupがpartitionを跨がないことを確認する。同じ外部splitを全Engineで使う。

探索へはtrainだけを渡し、Selectionは共通選定、Finalは選定後の最終評価に使う。pretrainedモデルが内部validationを必要とするならtrain内だけで分ける。比較前共通refitはtrain、最終refitはtrain＋Selectionを使う。

これは未見設計・未見条件groupの評価であり、純粋な一変数外挿試験とは異なる。Froude数や材齢の閾値でFinalを決める外挿試験を追加する場合は別splitとして設計し、同一形状・配合がFinalと学習側で共有されることの意味を明示する。初期版では追加しない。

## 5. 最小の検証セット

| 段階 | データ | 実行内容 | 合格・判定 |
| --- | --- | --- | --- |
| 通常pytest | 数十行の自作線形・有理式fixture | 係数・定義域・native変換・bundle・split | 固定した数値機能を検査。外部ダウンロード不要 |
| Adapter受入 | 小さな既知式＋Yacht train | native探索と共通AST予測 | export候補の照合。全Engineが同じ正解文字列を出す条件にはしない |
| 初回実証 | Yacht全partition | 基準式/mean/ridge＋PySR/PhySO | 共通比較表、凍結、保存、推論を一周 |
| 事前学習実証 | Yacht＋Airfoil | Flash-ANSR/RASR/PISRの対応範囲で比較 | asset・実効入力点数・native照合・誤差と時間。PISR未対応なら失敗理由を記録 |
| 非線形・相関入力 | Concrete | TorchSISSO/ParFam/ProGED等を追加 | 群分割での誤差、式サイズ、適格候補数 |
| 不確かさ | Yacht/Concrete | PySIPSのnative事後予測 | 区間被覆・幅、推定診断。共通refitと分離 |

通常のpytestは外部データ・GPU・重みを取得しない。取得スクリプトのためだけの大きなデータ管理層も作らない。三つの実データすべてに10Engineの組合せを必須化しない。

添付metadataのmean_predictor_rmseは、trainの目的変数平均によるtrain/Selectionだけの基準値であり、探索性能ではない。SelectionではYachtが15.943151、Airfoilが7.044350 dB、Concreteが14.891401 MPaとなった。Finalは件数・group数だけを記録し、モデル指標は選定凍結後のfinalizeで初めて計算する。この基準値より良いことだけを科学的な有用性の証明とはしない。

初回benchmarkは1 seed・各Engine最大300秒程度の作動確認から開始し、性能を比較すると決めた場合だけ事前固定した3 seed・同じ予算へ拡張する。外部データの性能をFinalで繰り返しチューニングしない。研究用の複数seed集計では、その評価プロトコル自体を先に固定する。

## 6. 事前学習との重複・構造回復

UCIやFeynmanは公開ベンチマークであり、事前学習や開発時の調整に使われていないと保証できない。今回の3件もmetadataでpretraining_overlap=unknownとした。公開データの好成績を、完全に未見の装置現象への汎化と主張しない。

Feynman/SRBenchは既知式の回復を測る追加候補だが、初期データセットへ大量に取り込まない。必要なら公式の対象式・元データを固定して少数追加し、真の式はscore専用ファイルへ隔離する。PISRの検索索引やpretrained学習データと重複する式は、既知式再発見の成績として区別する。合成fixtureで新しい点を生成しただけでは式構造の学習混入は解消しない。

## 7. 出典と配布条件

3件ともUCI公式ページはCC-BY-4.0と明記している。元の著者、UCI、DOIを引用し、本パッケージが列名変更・派生group・分割を追加したことを明示する。添付source.zipは元配布、table.csv等は今回の派生物。

- Yacht：Gerritsma, J., Onnink, R., & Versluis, A. (1981). [公式ページ](https://archive.ics.uci.edu/dataset/243/yacht+hydrodynamics) / DOI: 10.24432/C5XG7R。
- Airfoil：Brooks, T., Pope, D., & Marcolini, M. (1989). [公式ページ](https://archive.ics.uci.edu/dataset/291/airfoil+self+noise) / DOI: 10.24432/C5VW2C。
- Concrete：Yeh, I. (1998). [公式ページ](https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength) / DOI: 10.24432/C5PK67。
- 追加候補：[SRBench公式データ一覧](https://cavalab.org/srbench/datasets/)。今回は取得・検証していない。

raw ZIP・table・splitのSHA-256は各metadata.jsonへ保存済み。再生成時は公式列順と行数を検査し、変更があれば失敗させる。スナップショットの更新は新しいディレクトリへ行い、比較済みのデータを上書きしない。
