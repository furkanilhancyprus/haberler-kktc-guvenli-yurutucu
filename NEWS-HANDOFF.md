# Gerçek haber test akışı

**Haberler KKTC real news draft** iş akışını elle çalıştırmak, Vercel’in canlı API’sine tek bir editoryal haberin görselini yükler ve `news-handoff` çıktısını verir. Varsayılan haber, Meteoroloji Dairesi’nin 17–23 Kasım bülteninden doğrulanan yağmur tahminidir. İki bağlantı aynı resmî raporu aktarıyor. Görsel, olay fotoğrafı bulunmadığı için açıkça etiketlenmiş özgün illüstrasyondur.

Otomatik saatlik tetikleyici ancak `NEWS_DRAFT_PREPARATION_ENABLED=true` ile çalışır. Şu aşamada bu değişkeni açma. İş akışı yalnızca `news/inbox/*.json` içindeki doğrulanmış adaylardan en yenisini seçer. Haricî haber tarayıcısı veya Metricool oturumu yoktur. Haber yaşını Kıbrıs saatine göre denetler ve 24 saati geçmiş adayı atlar.

## İlk taslağı oluşturacak yetkili bağlantı

1. Actions çıktısındaki `newsId` ve Blob URL’sini doğrula. Anahtar `news:<newsId>` biçiminde sabittir.
2. Metricool takvimini oku. Aynı haberin daha önce yayımlanıp yayımlanmadığını metin ve kaynakla karşılaştır. İlk testin belirteci `[HKKTC TEST <newsId>]`.
3. Taslak oluşturmadan önce varsayılan dalda `news/state/<newsId>.json` dosyasını benzersiz adla oluştur. İçeriğinde `newsId`, `mediaId` ve `status: "claimed"` bulunur. Aynı dosya zaten varsa yeni taslak gönderme. Belirsiz sonuçta Metricool’da belirteci ara ve mevcut kaydı uzlaştır.
4. Metricool marka 7549135 için Facebook sağlayıcısıyla, görseli olan ve `draft:true`, `autoPublish:false` bir taslak oluştur. Taslağı Metricool’dan yeniden oku. Görseli `static.metricool.com` üzerinden indir ve JPEG olduğunu doğrula. Durum dosyasına `metricoolPostId`, doğrulanmış `metricoolMediaUrl` ve `status: "draft_verified"` yaz. Durum dosyasını güncellerken geçerli SHA’yı kullan.
5. Bu tek testin Blob’unu, bağımsız Metricool kopyası doğrulandıktan sonra yetkili Blob işlemiyle sil. Gerçek haberler için üretim temizliği kapalı kalır.

Metricool OAuth oturumu, ChatGPT’de bağlıdır. GitHub Actions bu bağlantıyı devralmaz. Ücretsiz doğrulama yolu, GitHub çıktısını mevcut ChatGPT Metricool bağlantısıyla taslağa bağlamaktır. Bağımsız saatlik planlama için çalıştırıcıya ayrıca geçerli bir Metricool OAuth yetkisi ve doğrulanmış haber girişi gerekir. Facebook otomatik yayını bu adımlardan ayrı bir onay gerektirir.
