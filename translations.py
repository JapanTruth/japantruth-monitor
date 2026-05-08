# JapanTruth 固有名詞翻訳辞書
# news_monitor.py から参照される

TRANSLATIONS = """
== 米国大統領・政権 ==
- Donald Trump=ドナルド・トランプ（米大統領）
- JD Vance=JD・ヴァンス（副大統領）
- Marco Rubio=マルコ・ルビオ（国務長官）
- Pete Hegseth=ピート・ヘグセス（国防長官）
- Scott Bessent=スコット・ベッセント（財務長官）
- Pam Bondi=パム・ボンディ（司法長官）
- Tulsi Gabbard=タルシー・ギャバード（国家情報長官）
- Kash Patel=カッシュ・パテル（FBI長官）
- Elon Musk=イーロン・マスク
- Steve Witkoff=スティーブ・ウィトコフ（中東・ウクライナ担当特使）
- Jared Kushner=ジャレッド・クシュナー（トランプ外交顧問）
- Karoline Leavitt=カロライン・レビット（ホワイトハウス報道官）
- John Ratcliffe=ジョン・ラトクリフ（CIA長官）
- Howard Lutnick=ハワード・ラトニック（商務長官）

== 米国議会・元政権 ==
- Mike Johnson=マイク・ジョンソン（下院議長）
- Hakeem Jeffries=ハキーム・ジェフリーズ（下院民主党院内総務）
- Chuck Schumer=チャック・シューマー（上院民主党院内総務）
- Mitch McConnell=ミッチ・マコネル（元上院共和党院内総務）
- Joe Biden=ジョー・バイデン（元大統領）
- Kamala Harris=カマラ・ハリス（元副大統領）
- Nancy Pelosi=ナンシー・ペロシ（元下院議長）
- Bernie Sanders=バーニー・サンダース
- Mark Hamill=マーク・ハミル
- Nikki Haley=ニッキー・ヘイリー
- Mike Pence=マイク・ペンス（元副大統領）

== ロシア ==
- Vladimir Putin=ウラジーミル・プーチン（大統領）
- Sergei Lavrov=セルゲイ・ラブロフ（外相）
- Dmitry Medvedev=ドミトリー・メドベージェフ
- Valery Gerasimov=ワレリー・ゲラシモフ（参謀総長）
- Kirill Dmitriev=キリル・ドミトリエフ（外交特使）

== ウクライナ・東欧 ==
- Volodymyr Zelensky=ウォロディミル・ゼレンスキー（大統領）
- Peter Magyar=ペーテル・マジャル（ハンガリー首相、2026年4月就任）
- Viktor Orban=ヴィクトル・オルバン（元ハンガリー首相）
- Donald Tusk=ドナルド・トゥスク（ポーランド首相）

== 西欧・EU ==
- Emmanuel Macron=エマニュエル・マクロン（フランス大統領）
- Marine Le Pen=マリーヌ・ル・ペン
- Friedrich Merz=フリードリヒ・メルツ（ドイツ首相）
- Olaf Scholz=オラフ・ショルツ（元ドイツ首相）
- Alice Weidel=アリス・ワイデル（AfD共同党首）
- Keir Starmer=キア・スターマー（英首相）
- Rishi Sunak=リシ・スナク（元英首相）
- Giorgia Meloni=ジョルジャ・メローニ（イタリア首相）
- Ursula von der Leyen=ウルズラ・フォン・デア・ライエン（欧州委員会委員長）
- Mark Rutte=マルク・ルッテ（NATO事務総長）

== 中東 ==
- Ali Khamenei=アリー・ハメネイ（イラン最高指導者）
- Masoud Pezeshkian=マスード・ペゼシュキアン（イラン大統領）
- Abbas Araghchi=アッバース・アラグチー（イラン外相）
- Benjamin Netanyahu=ベンヤミン・ネタニヤフ（イスラエル首相）
- Mohammed bin Salman=ムハンマド・ビン・サルマン（MBS）
- Recep Tayyip Erdogan=レジェップ・タイイップ・エルドアン（トルコ大統領）
- Ahmed al-Sharaa=アフマド・アル＝シャラア（シリア暫定指導者）
- Ismail Haniyeh=イスマイル・ハニヤ（元ハマス政治局長、2024年暗殺）
- Yahya Sinwar=ヤヒヤ・シンワル（元ハマス指導者、2024年死亡）
- Hassan Nasrallah=ハサン・ナスラッラー（元ヒズボラ書記長、2024年暗殺）

== 中国・東アジア ==
- Xi Jinping=習近平（国家主席）
- Li Qiang=李強（首相）
- Wang Yi=王毅（外相）
- Dong Jun=董軍（国防相）
- Kim Jong Un=金正恩（朝鮮労働党総書記）
- Lee Jae-myung=李在明（韓国大統領、2025年6月就任）
- Yoon Suk-yeol=尹錫悦（元韓国大統領、弾劾）
- Lai Ching-te=頼清徳（台湾総統）

== 日本 ==
- Sanae Takaichi=高市早苗（首相、第105代）
- Shigeru Ishiba=石破茂（元首相）
- Fumio Kishida=岸田文雄（元首相）

== 南・東南アジア ==
- Narendra Modi=ナレンドラ・モディ（インド首相）
- Prabowo Subianto=プラボウォ・スビアント（インドネシア大統領）
- Anutin Charnvirakul=アヌティン・チャーンウィラクン（タイ首相）
- Anthony Albanese=アンソニー・アルバニージー（オーストラリア首相）

== 中南米・アフリカ ==
- Nicolas Maduro=ニコラス・マドゥロ（元ベネズエラ大統領、米軍拘束中）
- Delcy Rodriguez=デルシー・ロドリゲス（ベネズエラ代行大統領）
- Claudia Sheinbaum=クラウディア・シェインバウム（メキシコ大統領）
- Luiz Inacio Lula da Silva=ルイス・イナシオ・ルラ・ダシルバ（ブラジル大統領）
- Javier Milei=ハビエル・ミレイ（アルゼンチン大統領）
- Cyril Ramaphosa=シリル・ラマポーザ（南アフリカ大統領）

== 国際機関・宗教 ==
- Antonio Guterres=アントニオ・グテーレス（国連事務総長）
- Tedros Adhanom=テドロス・アダノム（WHO事務局長）
- Jerome Powell=ジェローム・パウエル（FRB議長）
- Pope Leo XIV=教皇レオ14世（初のアメリカ人教皇、2025年5月就任）
- Fed / Federal Reserve=連邦準備制度（FRB）
- Hamas=ハマス, Hezbollah=ヒズボラ, Houthis=フーシ派

== テック ==
- Jensen Huang=ジェンスン・フアン（NVIDIA CEO）
- Mark Zuckerberg=マーク・ザッカーバーグ（Meta CEO）
- Sam Altman=サム・アルトマン（OpenAI CEO）
- Warren Buffett=ウォーレン・バフェット（Berkshire=バークシャー・ハサウェイ）

== スポーツ ==
- Shohei Ohtani=大谷翔平
- Kylian Mbappe=キリアン・エムバペ
"""
