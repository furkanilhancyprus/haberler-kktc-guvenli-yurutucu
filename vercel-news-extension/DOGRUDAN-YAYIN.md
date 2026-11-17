# Haberler KKTC doğrudan yayın

`POST /api/news/publish` doğrulanmış editoryal metni mevcut Vercel projesinde saklar. `POST /api/media/upload` üzerinden alınan temiz JPEG, kalıcı Blob adresine kopyalanır. Haber görünümü, ana sayfa, kategori ve Son Haberler aynı katalogdan sunulur. Eski haberlerin HTML dosyaları aynı adreslerden açılır.

## Yetkili çağrı

Yürütücüde `MEDIA_API_TOKEN` gizli ortam değişkeni olmalı. Ayrı `NEWS_API_TOKEN` tanımlanırsa haber ve Metricool durum uç noktaları onunla, görsel yükleme mevcut medya anahtarıyla çağrılır. Sunucu `BLOB_READ_WRITE_TOKEN` ve mevcut `MEDIA_ID_KEY` kullanır. `MEDIA_ID_KEY`, şifreli teslimat kaydını okumak için sabit kalmalıdır.

Hazırlanmış paket UTF-8 JSON içinde `external_id`, `title`, `content`, `summary`, `category`, `source_name`, `source_url`, `tags` ve `status: "published"` içerir. `external_id` aynı haber için sabittir. `--image` varsa CLI mevcut medya uç noktasını çağırıp `media_url` alanını doldurur. Önceden yüklenen JPEG için `media_url` aynı Vercel Blob deposundan alınabilir.

```sh
python news_client.py publish haber.json --image gorsel.jpg
```

CLI, haber sayfasını ve kalıcı JPEG'i HTTP üzerinden doğrular. Uygulama çağrısı `Authorization: Bearer …` ve `Idempotency-Key: news:<external_id>` kullanır. İlk kayıt 201, aynı içeriğin tekrarı 200 ve `created: false`, kimlik veya kaynak çakışması 409 döndürür. Önizleme testi için `NEWS_SERVICE_ORIGIN` ve yalnızca o dağıtıma ait geçici `NEWS_PREVIEW_SHARE` kullanılabilir. Üretim haberinde önizleme ayarlarını boş bırak.

## Site kaydından sonra Metricool

1. Doğrulanmış `news_url`, `media_url` ve `external_id` değerlerini al. Sosyal metinde haber bağlantısını kullan. Önce Metricool takviminde aynı haber bağlantısına bak.
2. Aynı yetkili yürütücüden `POST /api/news/metricool` veya `python news_client.py state durum.json` ile `{ "external_id": "…", "operation": "claim", "mode": "draft" }` gönder. Yalnızca `claimed: true` dönerse yeni gönderi oluştur.
3. Bağlı Metricool markası `7549135`, Facebook sağlayıcısı `facebook` ve test için `draft: true`, `autoPublish: false` kullan. Takvimden dönen kaydı tekrar oku, görseli ve gönderi kimliğini doğrula.
4. `operation: "result"`, `mode: "draft"`, `stage: "draft"` ve `post_id` ile kimliği kaydet. Sadece `external_id` gönderen çağrı saklanan durumu döndürür. Kesin reddedilen çağrı için `operation: "rejected"` tekrar denemeyi açar. Zaman aşımı veya belirsizlikte `operation: "uncertain"` kullan. `sending` veya `uncertain` durumunda aynı gönderiyi yeniden oluşturmak yerine takvimde haber bağlantısı ve kaydı uzlaştır.

Canlı sosyal gönderide `mode: "live"` yalnızca üretimde kabul edilir. Gerçek Facebook yayını açık yetki verildikten sonra bağlı Metricool hesabından yapılır. `scheduled` ve `published` durumlarını Metricool'da ilgili durum görüldükten sonra kaydet. Zamanlanmış görev, Python istemcisinin çalıştığı ve haber anahtarının güvenle sağlandığı bir ortam ile bağlı Metricool aracına ayrı ayrı erişebilmelidir.

## Dağıtım ve geri dönüş

- Son üretim kaynak envanterini al. Mevcut `public/`, `api/media.py`, medya servisi ve diğer kaynak dosyalarını koru. Bu paketteki yeni işlevleri, derleme komutunu ve yönlendirmeleri birleştir. Canlı ayarlarda bulunan cron ve yönlendirmeleri koru.
- `build-static.mjs` kaynak HTML'yi değiştirmeden derleme çıktısından yalnızca liste sayfalarının statik kopyalarını çıkarır. Aynı sayfalar Vercel Python işlevine şablon olarak paketlenir. Eski haber dosyaları statik olarak kalır.
- `python -m unittest discover -s tests` yerel testleri çalıştırır. `PYTHONPATH` içinde proje kökü varken `python tests/preview_smoke.py --id hkk-direct-test-… --image test.jpg` korumalı önizleme testi yapar. Alternatif olarak `--uploaded-url` önceden temizlenmiş Blob görselini kullanır. Test üretim alan adında çalışmayı reddeder.
- Üretim onayı verilince önizlemede doğrulanmış kaynağı son canlı sürümle karşılaştır. Başlangıç dağıtımı değişmişse birleştirip önizlemeyi tekrar test et. Üretim ve önizleme haber katalogları ayrıdır. Üretim onayı sonrası ilk test için onaylı gerçek bir haber kullan. Sorun olursa önceki READY dağıtımı Vercel'den geri yükle. Kalıcı haber kayıtları Blob'da korunur.
- Katalog tek bir koşullu yazımla güncellenir. 3 MB sınırında API yazmayı reddeder. Bu sınıra yaklaşmadan katalog bölümlenebilir veya mevcut bir veritabanına taşınabilir. Dağıtım değişiklikleri Git ile izlenebilir, günlük haber için GitHub ve yeni Vercel dağıtımı gerekmez.
