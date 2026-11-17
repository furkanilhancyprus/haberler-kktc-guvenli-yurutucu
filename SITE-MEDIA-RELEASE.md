# Haberler KKTC site ve görsel aktarımı

Canlı Vercel sitesi `src/public/` altında statik HTML ile çalışıyor. `src/api/media.py`, bağlı Vercel Blob deposuna yazıyor. cPanel için hazırlanmış PHP/MySQL yönetim paneli ayrı bir kaynak. Bu akış cPanel veritabanına veya Facebook Graph yayın uç noktalarına yazmaz.

## Haber paketi

Editör veya otomasyon şu alanları içeren UTF-8 JSON sağlar. `newsId` aynı olayın her denemesinde sabit kalır. `sourceUrls` tekil haber bağlantılarını içerir. `publishedAt` ve `scheduleAt` Kıbrıs yerel UTC ofsetini içeren ISO 8601 tarihidir. `verified` editoryal doğrulamanın sonucudur.

| Alan | Tür |
| --- | --- |
| `newsId`, `headline`, `category` | Metin |
| `paragraphs`, `sourceUrls`, `tags` | Metin listesi |
| `publishedAt`, `scheduleAt` | Ofsetli ISO 8601 |
| `verified` | `true` |
| `socialText` | Metricool paylaşım metni |

Kategoriler `gundem`, `dunya`, `siyaset`, `spor`, `ekonomi`, `teknoloji`, `yasam`, `magazin`.

## Önizleme ve üretim

1. `haberler-kktc.vercel.app` alan adına bağlı üretim dağıtımının kimliğini ve `src/` kaynak envanterini yetkili Vercel bağlantısından al. Listeyi `snapshot.json` olarak kaydet. Ana sayfayı, Son Haberler'i, ilgili kategori sayfasını ve bir mevcut haber şablonunu aynı sürümden özgün baytlarıyla `sources/public/...` altına al. Derleyici değiştirilecek kaynakların SHA1 özetlerini kontrol eder.
2. `MEDIA_API_TOKEN` değerini yürütücünün gizli ortam değişkeni olarak ver. Yükleme, yeniden kodlama ve manifest hazırlığı için:

   ```sh
   python site_release.py --snapshot snapshot.json --package package.json \
     --sources sources --template public/haber-ORNEK.html \
     --image editorial.jpg --upload-image --output release
   ```

   Mevcut yükleme yanıtı varsa `--image ... --upload-image` yerine `--blob-receipt upload.json` kullan. Çıktı özgün site kaynaklarının özetlerini ve üretilen dosyaları içeren `deployment-files.json` ile doğrulama için `verify-sha1.json` dosyasıdır.
3. `deployment-files.json` dosyalarını aynı Vercel projesinde önizleme olarak dağıt. Yetkili Vercel bağlantısıyla haber metnini, kaynakları, görseli, arşivi, kategoriyi ve ana sayfayı kontrol et. Üretim alan adının önceki başlangıç dağıtımına bağlı olduğunu yeniden doğrula. Değiştiyse manifesti yeni kaynaklardan üret. Test haberini üretime taşıma.
4. Onaylanmış gerçek haber üretimdeyse herkese açık sayfaları ve JPEG'i kimlik bilgisi olmadan doğrula:

   ```sh
   python site_release.py --package package.json --output release --verify-production
   ```

   Bu komut yalnızca beş dosyanın SHA1 özeti eşleştiğinde `metricool-handoff.json` üretir. Metricool görseli kalıcı site adresinden alır. Geçici Blob temizliği site kopyasını etkilemez.

## Metricool

Yetkili Metricool bağlayıcısında marka `7549135` ve sağlayıcı `facebook` kullan. `news/state/<newsId>.json` kaydını varsayılan dalda benzersiz olarak oluşturmadan yeni taslak gönderme. Ağ veya yanıt hatasında önce Metricool takviminde aynı haber anahtarını sorgula. Taslak oluşturup geri okuduktan sonra kayda gönderi ID'sini, plan saatini, durumunu ve doğrulanmış Metricool görsel adresini ekle. `draft:true` ve `autoPublish:false` test sırasında zorunludur.

GitHub Actions, ChatGPT'nin Metricool oturumunu kendiliğinden devralmaz. Bu dal mevcut saatlik çalışmaları veya üretim yayın ayarlarını değiştirmez. Bağlı Metricool istemcisi ücretsiz erişim yoludur. Bağımsız REST yürütücüsü için Metricool hesabında ilgili API yetkisi gerekir.

Vercel'in mevcut medya işlevi `BLOB_READ_WRITE_TOKEN`, `MEDIA_API_TOKEN` ve kararlı `MEDIA_ID_KEY` kullanır. Vercel dışındaki yürütücü yalnızca `MEDIA_API_TOKEN` alır. `.env.example` anahtar adını gösterir ve uygulama `.env` dosyasını kendiliğinden yüklemez.

## Geliştirici testi

Eski medya testleri `haberler-kktc-yayin-entegrasyonu` dizininde `python -m unittest discover -s tests` ile çalıştırılır. Site derleyicisini canlı üretim envanterinden örnek bir haberle sınamak için ilk üç adımı güvenli önizleme olarak çalıştır. Aynı `newsId` önizleme envanterinde bulunuyorsa derleyicinin `NEWS_ALREADY_PRESENT` ile durduğunu doğrula.
