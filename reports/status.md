# 当前曲谱检查清单

检查范围：23,199 首曲目，55,838 份 setting。数据文件为当前 fork 的 CSV、JSON 和 SQLite。

这里将确定修改、待核对项和不按源谱错误处理的情况分开。未修正的候选并不等于已经确认的人为手误。

| 分类 | Setting 数 | 完整明细 |
|---|---:|---|
| 已修正 | 275 | [fixed.csv](fixed.csv) |
| 尚需核对 | 3942 | [review.csv](review.csv) |
| 弱起、段尾与反复边界记录 | 24421 | [boundaries.csv](boundaries.csv) |
| 暂不支持的语法或空旋律 | 6515 | [unsupported.csv](unsupported.csv) |
| 播放或解析兼容记录 | 3529 | [playback.csv](playback.csv) |

已修正的 setting 中，有 36 份还包含其他待核对项。因此各类数量不能相加当作独立曲谱总数。所有 CSV 均包含原网站链接和当前完整 ABC；fixed.csv 另有修改前 ABC。

## 已修正的类型

| 类型 | 处数 |
|---|---:|
| 小节线错位 | 7 |
| 漏写小节线 | 211 |
| 音长数字或斜线手误 | 72 |
| 误入的控制字符 | 19 |

## 自动检查做了什么

- 用有理数累计音长，避免浮点误差造成缺拍误报。
- 小节线补写或移动，需要同曲、同调中独立存在的完整小节作佐证。
- 音长手误限于一个数字或斜线的改动，还要求整个修正小节和相邻乐句有唯一匹配。
- 保留音高、连音、装饰、作者与其他元数据。不猜音符，不补休止符，不推断新拍号。
- 用关闭自动修复的独立 ABC 播放解析器对比每个事件。意外的音高、休止、连音或时值变化会阻止写入。
- 反复扫描直至没有新的可验证改动；最后核对全部三种导出格式及数据库完整性。

独立播放检查保留了 3 个未通过的候选，见 [拒绝原因](../checks/rejected.json)。例如移动小节线可能重置临时升降号，因此时值凑齐本身不构成修改依据。

首尾连续播放相关的调整继续只作为 App 行为，不计入源谱修正。内部短小节也可能来自有意的曲式或混合拍号，缺少证据时保留。暂不支持并不表示原谱错误。

## 待核对示例

| 曲目 | Setting | 检查项 |
|---|---|---|
| 'Ma' McNulty's Favourite | [55813](https://thesession.org/tunes/26102#setting55813) | 内部短小节候选; 内部小节时值不足 |
| 101 To Dublin | [50416](https://thesession.org/tunes/19336#setting50416) | 内部小节时值超出 |
| 101 To Dublin | [38079](https://thesession.org/tunes/19336#setting38079) | 内部小节时值超出 |
| 10th Bat Crossing Rhine | [18649](https://thesession.org/tunes/7078#setting18649) | 内部小节时值超出 |
| 1st Floor March | [42485](https://thesession.org/tunes/21293#setting42485) | 内部小节时值不足 |
| 2-Rivisjenkka | [32371](https://thesession.org/tunes/16424#setting32371) | 短音符音长候选 |
| 23 | [34482](https://thesession.org/tunes/17726#setting34482) | 拍号或曲式需要核对 |
| 23 | [34317](https://thesession.org/tunes/17726#setting34317) | 内部短小节候选; 内部小节时值不足 |
| 4 Minutes 33 Seconds | [15743](https://thesession.org/tunes/2399#setting15743) | 内部小节时值超出 |
| 4 Minutes 33 Seconds | [55757](https://thesession.org/tunes/2399#setting55757) | 内部小节时值超出 |
| 42nd Highlanders Farewell | [28873](https://thesession.org/tunes/15410#setting28873) | 拍号或曲式需要核对 |
| 51st Highland Division, The | [38610](https://thesession.org/tunes/19573#setting38610) | 内部小节时值超出 |
| 72nd Highlanders' Farewell To Aberdeen, The | [6970](https://thesession.org/tunes/6970#setting6970) | 内部小节时值不足 |
| 78 Eatonwood Green | [43643](https://thesession.org/tunes/21785#setting43643) | 内部小节时值超出; 漏写小节线 |
| 79th's Farewell To Gibraltar | [5318](https://thesession.org/tunes/5318#setting5318) | 内部小节时值不足 |
| A Breton In Paris | [20892](https://thesession.org/tunes/12500#setting20892) | 内部短小节候选; 内部小节时值不足 |
| A Builder Of Bridges | [39057](https://thesession.org/tunes/8602#setting39057) | 内部小节时值超出 |
| A Chomaraigh Aoibhinn O | [48054](https://thesession.org/tunes/15714#setting48054) | 内部小节时值超出 |
| A Day At The Carnival | [41510](https://thesession.org/tunes/20882#setting41510) | 内部小节时值不足 |
| A Dhia Na Nollaig | [26964](https://thesession.org/tunes/14630#setting26964) | 内部短小节候选; 内部小节时值不足 |
| A Dram At The Wake | [23732](https://thesession.org/tunes/9105#setting23732) | 内部小节时值超出 |
| A Farruquiña | [43829](https://thesession.org/tunes/21838#setting43829) | 内部小节时值超出 |
| A Farruquiña | [43827](https://thesession.org/tunes/21838#setting43827) | 内部小节时值超出 |
| A Happy Day In June | [43454](https://thesession.org/tunes/21532#setting43454) | 拍号或曲式需要核对 |
| A Jig For Kim | [30014](https://thesession.org/tunes/15947#setting30014) | 内部小节时值不足 |

完整列表见上方 CSV。修正的完整补丁见 [changes](../changes/)，数据及播放检查结果见 [checks](../checks/)。
