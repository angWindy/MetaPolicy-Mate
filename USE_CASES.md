# BẢNG ĐẶC TẢ USE CASE

## Hệ thống P-234 — Trợ lý hỏi đáp quy chế, quy định

# 0. Phạm vi hệ thống (đã chốt)

**Phạm vi triển khai hiện tại:**

- Quản lý danh mục văn bản quy chế, quy định và văn bản nguồn (Nhóm A0).
- Quản lý tri thức ở cấp điều khoản phục vụ RAG: số hóa, chunk, metadata, phiên bản và tra cứu (Nhóm A).
- Chatbot hỏi đáp quy chế, quy định dựa trên RAG (Nhóm D).
- Giám sát / đánh giá độ chính xác hệ thống (Nhóm F).
- Quản lý người dùng và phân quyền (Nhóm G).
- Ghi nhận phản hồi khi phát hiện câu trả lời sai (Nhóm H).

# 1. Danh sách tác nhân (Actors)

| **Tác nhân** | **Vai trò trong hệ thống** |
| --- | --- |
| **Người dùng** | Hỏi đáp và tra cứu quy chế, quy định; tiếp tục hỏi sâu trong cùng phiên; báo lỗi khi phát hiện câu trả lời không chính xác. |
| **Chuyên gia phê duyệt** | Quản lý văn bản; rà soát/phê duyệt metadata điều khoản; quản lý hiệu lực, phiên bản và lịch sử thay đổi của văn bản. |
| **Admin hệ thống** | Quản trị kỹ thuật: tài khoản, vai trò, phân quyền và giám sát hoạt động hệ thống. |
| **Hệ thống** | Tác nhân tự động: xử lý/chunk văn bản, trích xuất metadata, retrieval, sinh câu trả lời có căn cứ và ghi log. |

# 2. Danh sách tổng hợp Use Case theo nhóm chức năng

*Tổng cộng 6 nhóm chức năng (A0, A, D, F, G, H), gồm 21 use case, với các use case như sau:*

| **Mã UC** | **Tên Use Case** | **Actor chính** | **Ghi chú** |
| --- | --- | --- | --- |
| **NHÓM A0 — Quản lý danh mục văn bản quy chế/quy định** |  |  |  |
| **A0-01** | Quản lý danh mục văn bản quy chế/quy định | Chuyên gia phê duyệt, Admin | *Mã hiệu, ngày ban hành, trạng thái hiệu lực* |
| **A0-02** | Nạp / thay thế văn bản nguồn | Chuyên gia phê duyệt | *Upload file gốc chính thức* |
| **A0-03** | Quản lý quan hệ thay thế/sửa đổi giữa văn bản | Chuyên gia phê duyệt | *Liên kết văn bản A → sửa đổi/thay thế bởi B* |
| **A0-04** | Theo dõi hiệu lực và cập nhật văn bản mới | Chuyên gia phê duyệt | *Khai báo khi có văn bản mới ban hành* |
| **A0-05** | Quản lý phạm vi áp dụng giữa các văn bản | Chuyên gia phê duyệt | *Quan hệ và phạm vi áp dụng giữa các văn bản* |
| **A0-06** | Xem lịch sử thay đổi văn bản (changelog) | Chuyên gia phê duyệt, Admin | *Audit cấp văn bản* |
| **NHÓM A — Quản lý tri thức văn bản (cấp điều khoản)** |  |  |  |
| **A-01** | Số hóa và chunk văn bản theo điều khoản | Admin (kỹ thuật) | *Giữ nguyên số hiệu điều/khoản/điểm* |
| **A-02** | Trích xuất metadata bán tự động | Hệ thống | *Draft metadata, cross-reference* |
| **A-03** | Rà soát và phê duyệt metadata điều khoản | Chuyên gia phê duyệt | *Xác nhận trước khi đưa vào sử dụng* |
| **A-04** | Quản lý phiên bản điều khoản | Chuyên gia phê duyệt | *is_current, effective_from/to* |
| **A-05** | Xây dựng và rà soát bảng threshold tĩnh | Chuyên gia phê duyệt | *Bảng tra cứu đã kiểm chứng thủ công* |
| **A-06** | Tìm kiếm / tra cứu văn bản (hybrid retrieval) | Người dùng, Chuyên gia phê duyệt | *Semantic + keyword + filter metadata* |
| **NHÓM D — Tương tác người dùng (Interaction)** |  |  |  |
| **D-01** | Hỏi đáp tự do về quy chế/quy định | Người dùng | *Dùng RAG pipeline, có trích dẫn nguồn* |
| **D-04** | Hỏi sâu vào nội dung/câu trả lời cụ thể | Người dùng | *Dùng session state đã lưu* |
| **NHÓM F — Quản trị & vận hành (System Administration)** |  |  |  |
| **F-04** | Giám sát / đánh giá độ chính xác hệ thống | Admin, Chuyên gia phê duyệt | *Đối chiếu log và phản hồi với kết quả thực tế* |
| **NHÓM G — Quản lý người dùng và phân quyền** |  |  |  |
| **G-01** | Quản lý tài khoản người dùng | Admin | *Tạo/sửa/khóa tài khoản* |
| **G-02** | Quản lý vai trò (role) | Admin | *Quản lý các vai trò sử dụng hệ thống* |
| **G-03** | Phân quyền theo chức năng (RBAC) | Admin | *Gán quyền theo chức năng của hệ thống* |
| **G-04** | Xác thực và quản lý phiên đăng nhập | Hệ thống | *Login/logout, session timeout* |
| **G-05** | Ghi log hoạt động người dùng | Hệ thống | *Theo dõi hoạt động và phục vụ truy vết* |
| **NHÓM H — Phản hồi hệ thống** |  |  |  |
| **H-08** | Báo lỗi câu trả lời sai | Người dùng, Chuyên gia phê duyệt | *Gắn cờ câu trả lời hệ thống cần rà soát* |

# 3. Đặc tả chi tiết các Use Case

*Phần dưới đây đặc tả đầy đủ toàn bộ các use case còn lại trong danh sách P-234 ở Mục 2. Nội dung Nhóm A0 được chuyển từ file đặc tả A0 đã cung cấp và chỉnh thuật ngữ PCCC/quy chuẩn sang văn bản quy chế, quy định của P-234; các nhóm còn lại được hoàn thiện theo đúng các UC đã có trong danh sách, không bổ sung UC mới.*

### UC-A0-01 — Quản lý danh mục văn bản quy chế/quy định

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt, Admin |
| **Mô tả tóm tắt** | Xem, tìm kiếm và cập nhật metadata của văn bản quy chế/quy định (mã hiệu, tên đầy đủ, cơ quan ban hành, ngày ban hành, ngày hiệu lực, trạng thái hiệu lực) — danh mục trung tâm dùng chung cho toàn hệ thống, là nơi hiển thị tổng hợp các use case khác của Nhóm A0. |
| **Điều kiện tiên quyết** | Người dùng đã đăng nhập với quyền Chuyên gia phê duyệt hoặc Admin. |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt/Admin chọn "Danh mục văn bản".<br>2. Hệ thống hiển thị danh sách văn bản, hỗ trợ tìm kiếm/lọc theo mã hiệu, trạng thái hiệu lực, khoảng ngày ban hành.<br>3. Người dùng chọn xem chi tiết một văn bản: hệ thống hiển thị đầy đủ metadata, quan hệ thay thế/sửa đổi (A0-03), phạm vi áp dụng (A0-05), lịch sử thay đổi (A0-06).<br>4. Người dùng chỉnh sửa metadata khi cần hiệu chỉnh sai sót; trạng thái hiệu lực được cập nhật thông qua A0-03/A0-04.<br>5. Hệ thống lưu thay đổi, ghi nhận vào changelog (A0-06). |
| **Luồng ngoại lệ** | Nếu người dùng cố sửa mã hiệu trùng với một văn bản khác đang hiệu lực → hệ thống báo lỗi, không lưu thay đổi. |
| **Điều kiện hậu quyết** | Danh mục văn bản được cập nhật chính xác, phản ánh đúng trạng thái hiện tại, sẵn sàng làm cơ sở tham chiếu cho A0-02 đến A0-06 và Nhóm A. |

---

### UC-A0-02 — Nạp / thay thế văn bản nguồn

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Nạp file văn bản quy chế/quy định gốc vào hệ thống, làm cơ sở cho các bước chunk và xử lý nội dung tiếp theo. |
| **Điều kiện tiên quyết** | Người dùng đã đăng nhập với quyền Chuyên gia phê duyệt; có file chính thức của văn bản cần nạp. |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt chọn chức năng “Nạp văn bản mới”.<br>2. Nhập thông tin văn bản: mã hiệu, tên đầy đủ, cơ quan ban hành, ngày ban hành, ngày hiệu lực.<br>3. Upload file văn bản gốc.<br>4. Hệ thống lưu file, tạo bản ghi trong Danh mục văn bản (A0-01) với trạng thái “chờ xử lý nội dung”.<br>5. Nếu văn bản này thay thế/sửa đổi một văn bản đã có, khai báo quan hệ (liên kết A0-03).<br>6. Hệ thống ghi nhận vào changelog (A0-06). |
| **Luồng ngoại lệ** | Nếu file không đúng định dạng được hệ thống hỗ trợ hoặc trùng mã hiệu với văn bản đang hiệu lực → hệ thống báo lỗi, không tạo bản ghi. |
| **Điều kiện hậu quyết** | Văn bản mới xuất hiện trong Danh mục văn bản, sẵn sàng để chuyển sang bước chunk nội dung (A-01). |

---

### UC-A0-03 — Quản lý quan hệ thay thế/sửa đổi giữa văn bản

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Khai báo và quản lý quan hệ thay thế/sửa đổi giữa các văn bản, đảm bảo hệ thống xác định đúng văn bản đang hiệu lực. |
| **Điều kiện tiên quyết** | Cả văn bản nguồn và văn bản đích đã tồn tại trong Danh mục văn bản (A0-01); văn bản nguồn đã được nạp (A0-02). |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt chọn văn bản nguồn (văn bản mới).<br>2. Chọn văn bản đích (văn bản bị thay thế/sửa đổi).<br>3. Chọn loại quan hệ: "thay thế toàn bộ" hoặc "sửa đổi một phần", kèm ghi chú phạm vi nếu cần.<br>4. Hệ thống lưu quan hệ; nếu là "thay thế toàn bộ" → cập nhật trạng thái văn bản đích.<br>5. Hệ thống ghi nhận vào changelog (A0-06). |
| **Luồng ngoại lệ** | Nếu văn bản đích đã có quan hệ "bị thay thế toàn bộ" bởi một văn bản khác đang hiệu lực → hệ thống cảnh báo xung đột, yêu cầu xác nhận trước khi ghi đè quan hệ. |
| **Điều kiện hậu quyết** | Quan hệ thay thế/sửa đổi được lưu, trạng thái hiệu lực của các văn bản liên quan được cập nhật nhất quán, phục vụ tra cứu (A-06) và theo dõi hiệu lực (A0-04). |

---

### UC-A0-04 — Theo dõi hiệu lực và cập nhật văn bản mới

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Theo dõi tình trạng hiệu lực và ghi nhận khi có văn bản mới được ban hành để kịp thời cập nhật kho tri thức, tránh sử dụng văn bản lỗi thời. |
| **Điều kiện tiên quyết** | Chuyên gia phê duyệt xác định có văn bản mới ban hành hoặc văn bản hiện có sắp/hết hiệu lực. |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt khai báo thông tin văn bản mới và văn bản hiện hành bị ảnh hưởng.<br>2. Hệ thống ghi nhận thông tin chờ xử lý.<br>3. Hệ thống rà soát ngày hiệu lực của các văn bản trong danh mục.<br>4. Chuyên gia phê duyệt xử lý bằng cách nạp văn bản mới (A0-02), khai báo quan hệ thay thế/sửa đổi (A0-03), hoặc cập nhật trạng thái phù hợp.<br>5. Hệ thống ghi nhận thay đổi vào changelog (A0-06). |
| **Luồng ngoại lệ** | Nếu văn bản đã hết hiệu lực nhưng văn bản thay thế chưa được nạp → hệ thống vẫn giữ trạng thái cần xử lý để Chuyên gia phê duyệt tiếp tục cập nhật. |
| **Điều kiện hậu quyết** | Trạng thái hiệu lực của danh mục được duy trì cập nhật, giảm rủi ro hệ thống tra cứu và trả lời dựa trên văn bản lỗi thời. |

---

### UC-A0-05 — Quản lý phạm vi áp dụng giữa các văn bản

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Khai báo quan hệ và phạm vi áp dụng giữa các văn bản, làm cơ sở xác định các văn bản liên quan khi tra cứu và hỏi đáp. |
| **Điều kiện tiên quyết** | Các văn bản liên quan đã tồn tại trong Danh mục văn bản (A0-01). |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt chọn văn bản nguồn cần khai báo phạm vi áp dụng.<br>2. Chọn các văn bản liên quan và ghi rõ phạm vi áp dụng hoặc nội dung được viện dẫn.<br>3. Hệ thống lưu quan hệ áp dụng gắn với phiên bản văn bản nguồn.<br>4. Hệ thống ghi nhận vào changelog (A0-06). |
| **Luồng ngoại lệ** | Nếu văn bản liên quan chưa có trong Danh mục → hệ thống yêu cầu nạp văn bản đó trước qua A0-02, không lưu quan hệ với văn bản chưa tồn tại. |
| **Điều kiện hậu quyết** | Quan hệ phạm vi áp dụng được lưu, phục vụ mở rộng cross-reference khi tra cứu/hỏi đáp (A-06, D-01). |

---

### UC-A0-06 — Xem lịch sử thay đổi văn bản (changelog)

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt, Admin |
| **Mô tả tóm tắt** | Xem toàn bộ lịch sử thay đổi ở cấp văn bản: tạo mới, cập nhật metadata, nạp/thay thế file, thay đổi trạng thái và quan hệ giữa các văn bản, phục vụ audit và truy vết. |
| **Điều kiện tiên quyết** | Đã có ít nhất một thao tác thay đổi được ghi nhận đối với văn bản cần xem. |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt/Admin chọn một văn bản trong Danh mục (A0-01), chọn "Lịch sử thay đổi".<br>2. Hệ thống hiển thị các thay đổi theo thời gian: hành động, người thực hiện, thời điểm và chi tiết thay đổi.<br>3. Người dùng có thể lọc theo loại hành động hoặc khoảng thời gian.<br>4. Người dùng xem chi tiết một bản ghi thay đổi, gồm giá trị trước/sau nếu có. |
| **Luồng ngoại lệ** | Không có ngoại lệ nghiệp vụ — đây là chức năng chỉ đọc; các bản ghi changelog không thể chỉnh sửa hoặc xóa. |
| **Điều kiện hậu quyết** | Người dùng có cái nhìn đầy đủ về lịch sử thay đổi của văn bản, phục vụ audit cấp văn bản. |

---

### UC-A-01 — Số hóa và chunk văn bản theo điều khoản

| | |
|---|---|
| **Actor** | Admin (kỹ thuật) |
| **Mô tả tóm tắt** | Xử lý văn bản nguồn thành các đoạn dữ liệu theo cấu trúc điều/khoản/điểm để phục vụ lưu trữ, tìm kiếm và RAG, đồng thời giữ được tham chiếu về văn bản gốc. |
| **Điều kiện tiên quyết** | Văn bản nguồn đã được nạp vào hệ thống (A0-02). |
| **Luồng sự kiện chính** | 1. Admin chọn văn bản cần xử lý.<br>2. Hệ thống đọc nội dung văn bản và tách theo cấu trúc điều/khoản/điểm.<br>3. Hệ thống tạo các chunk và giữ thông tin tham chiếu về văn bản, số điều/khoản/điểm và vị trí nguồn.<br>4. Hệ thống lưu các chunk để chuyển sang bước trích xuất/rà soát metadata (A-02/A-03). |
| **Luồng ngoại lệ** | Nếu một phần nội dung không thể xác định đúng cấu trúc → hệ thống ghi nhận phần chưa xử lý chính xác để Admin kiểm tra, không tự gán sai số hiệu điều/khoản/điểm. |
| **Điều kiện hậu quyết** | Các chunk của văn bản được tạo và liên kết với văn bản nguồn, sẵn sàng cho metadata và retrieval. |

---

### UC-A-02 — Trích xuất metadata bán tự động

| | |
|---|---|
| **Actor** | Hệ thống |
| **Mô tả tóm tắt** | Trích xuất metadata cần thiết từ nội dung điều khoản/chunk để hỗ trợ quản lý và retrieval. |
| **Điều kiện tiên quyết** | Văn bản đã được chunk (A-01). |
| **Luồng sự kiện chính** | 1. Hệ thống lấy nội dung từng chunk.<br>2. Hệ thống trích xuất metadata và các cross-reference có thể nhận diện từ nội dung.<br>3. Hệ thống lưu kết quả ở trạng thái chờ rà soát.<br>4. Kết quả được chuyển cho Chuyên gia phê duyệt qua A-03. |
| **Luồng ngoại lệ** | Nếu hệ thống không xác định được metadata hoặc cross-reference đủ rõ → trường tương ứng được để ở trạng thái chưa xác định để rà soát, không tự tạo thông tin không có căn cứ. |
| **Điều kiện hậu quyết** | Metadata draft được lưu và sẵn sàng để Chuyên gia phê duyệt rà soát. |

---

### UC-A-03 — Rà soát và phê duyệt metadata điều khoản

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Rà soát metadata được hệ thống trích xuất trước khi đưa dữ liệu điều khoản vào sử dụng cho retrieval. |
| **Điều kiện tiên quyết** | Đã có chunk và metadata draft từ A-01/A-02. |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt mở danh sách metadata chờ rà soát.<br>2. Đối chiếu metadata với nội dung văn bản nguồn.<br>3. Chỉnh sửa thông tin chưa chính xác nếu cần.<br>4. Xác nhận/phê duyệt metadata.<br>5. Hệ thống lưu trạng thái phê duyệt và thông tin người rà soát. |
| **Luồng ngoại lệ** | Nếu metadata không thể xác nhận từ văn bản nguồn → Chuyên gia phê duyệt không phê duyệt và yêu cầu xử lý lại dữ liệu liên quan. |
| **Điều kiện hậu quyết** | Metadata đã phê duyệt sẵn sàng được sử dụng cho tìm kiếm/tra cứu (A-06). |

---

### UC-A-04 — Quản lý phiên bản điều khoản

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Quản lý các phiên bản của điều khoản khi văn bản được sửa đổi/thay thế để retrieval sử dụng đúng nội dung theo trạng thái hiệu lực. |
| **Điều kiện tiên quyết** | Văn bản và điều khoản đã tồn tại; có thay đổi phiên bản hoặc quan hệ sửa đổi/thay thế từ Nhóm A0. |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt chọn điều khoản cần quản lý phiên bản.<br>2. Hệ thống hiển thị các phiên bản và thông tin hiệu lực.<br>3. Khi có phiên bản mới, hệ thống lưu phiên bản mới thay vì ghi đè nội dung cũ.<br>4. Chuyên gia phê duyệt xác nhận trạng thái hiện hành và khoảng hiệu lực.<br>5. Hệ thống cập nhật thông tin phiên bản phục vụ retrieval. |
| **Luồng ngoại lệ** | Nếu khoảng hiệu lực giữa các phiên bản bị chồng lấn hoặc không hợp lệ → hệ thống báo lỗi và không cho xác nhận cho đến khi được chỉnh sửa. |
| **Điều kiện hậu quyết** | Lịch sử phiên bản điều khoản được giữ lại; hệ thống xác định được phiên bản hiện hành để tra cứu. |

---

### UC-A-05 — Xây dựng và rà soát bảng threshold tĩnh

| | |
|---|---|
| **Actor** | Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Xây dựng và duy trì bảng threshold tĩnh từ các điều khoản đã được rà soát, dùng làm dữ liệu tra cứu có cấu trúc và đã được kiểm chứng thủ công. Threshold chỉ được đưa vào sử dụng sau khi Chuyên gia phê duyệt đối chiếu với văn bản nguồn. |
| **Điều kiện tiên quyết** | Điều khoản/chunk nguồn đã tồn tại từ A-01; metadata liên quan đã được rà soát/phê duyệt qua A-03; phiên bản điều khoản và khoảng hiệu lực được quản lý qua A-04 khi có nhiều phiên bản. |
| **Luồng sự kiện chính** | 1. Chuyên gia phê duyệt chọn điều khoản có nội dung định lượng cần đưa vào bảng threshold.<br>2. Hệ thống hiển thị nội dung điều khoản nguồn và metadata liên quan để đối chiếu.<br>3. Chuyên gia nhập hoặc hiệu chỉnh threshold tĩnh, gồm giá trị/điều kiện áp dụng và tham chiếu tới điều khoản nguồn.<br>4. Hệ thống kiểm tra dữ liệu bắt buộc và quan hệ với phiên bản điều khoản hiện hành.<br>5. Chuyên gia rà soát lại threshold với văn bản nguồn và xác nhận.<br>6. Hệ thống lưu threshold đã kiểm chứng để phục vụ tra cứu có cấu trúc và các chức năng có nhu cầu sử dụng dữ liệu định lượng về sau. |
| **Luồng ngoại lệ** | Nếu threshold không thể xác nhận trực tiếp từ điều khoản nguồn, thiếu điều kiện áp dụng, hoặc có dữ liệu mâu thuẫn/chồng lấn với threshold hiện hành trong cùng phạm vi áp dụng → hệ thống không cho xác nhận cho đến khi Chuyên gia phê duyệt xử lý. |
| **Điều kiện hậu quyết** | Threshold đã xác nhận được lưu cùng tham chiếu điều khoản/phiên bản nguồn và trạng thái hiệu lực tương ứng; dữ liệu cũ không bị ghi đè khi cần giữ lịch sử phiên bản. |

### UC-A-06 — Tìm kiếm / tra cứu văn bản (hybrid retrieval)

| | |
|---|---|
| **Actor** | Người dùng, Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Tìm kiếm nội dung liên quan trong kho tri thức bằng kết hợp semantic search, keyword search và metadata để cung cấp ngữ cảnh cho tra cứu và hỏi đáp. |
| **Điều kiện tiên quyết** | Kho tri thức đã có các chunk có thể sử dụng từ Nhóm A. |
| **Luồng sự kiện chính** | 1. Người dùng hoặc hệ thống gửi nội dung cần tìm kiếm.<br>2. Hệ thống áp dụng bộ lọc metadata phù hợp.<br>3. Hệ thống thực hiện semantic search và keyword search.<br>4. Hệ thống tổng hợp/xếp hạng các kết quả liên quan và xử lý cross-reference khi có.<br>5. Hệ thống trả về các đoạn nguồn cùng thông tin văn bản/điều khoản để sử dụng trực tiếp hoặc cung cấp cho D-01. |
| **Luồng ngoại lệ** | Nếu không tìm được kết quả đủ liên quan → hệ thống trả về trạng thái không có căn cứ phù hợp, không tự tạo nguồn. |
| **Điều kiện hậu quyết** | Các đoạn nguồn liên quan và metadata tham chiếu được trả về cho chức năng tra cứu hoặc RAG. |

---

### UC-D-01 — Hỏi đáp tự do về quy chế/quy định

| | |
|---|---|
| **Actor** | Người dùng |
| **Mô tả tóm tắt** | Cho phép người dùng đặt câu hỏi trực tiếp về nội dung quy chế, quy định và các văn bản có trong kho tri thức P-234. |
| **Điều kiện tiên quyết** | Người dùng đã đăng nhập. |
| **Luồng sự kiện chính** | 1. Người dùng nhập câu hỏi tự do.<br>2. Hệ thống truy vấn RAG pipeline (A-06): lọc theo metadata, hybrid search và xử lý cross-reference.<br>3. Hệ thống tổng hợp câu trả lời dựa trên nội dung được retrieve.<br>4. Hệ thống hiển thị câu trả lời kèm thông tin văn bản/điều khoản liên quan. |
| **Luồng ngoại lệ** | Nếu không tìm được nội dung liên quan → hệ thống trả lời rõ không có căn cứ trong kho tri thức hiện có, không tự suy diễn. |
| **Điều kiện hậu quyết** | Người dùng nhận được câu trả lời có căn cứ và có thể tiếp tục hỏi thêm trong cùng phiên. |

---

### UC-D-04 — Hỏi sâu vào nội dung/câu trả lời cụ thể

| | |
|---|---|
| **Actor** | Người dùng |
| **Mô tả tóm tắt** | Cho phép người dùng đặt câu hỏi tiếp theo dựa trên nội dung và ngữ cảnh của phiên hỏi đáp hiện tại. |
| **Điều kiện tiên quyết** | Đã có phiên hỏi đáp và ít nhất một câu hỏi/câu trả lời trước đó. |
| **Luồng sự kiện chính** | 1. Người dùng nhập câu hỏi tiếp theo.<br>2. Hệ thống lấy ngữ cảnh cần thiết từ session state đã lưu.<br>3. Hệ thống thực hiện retrieval (A-06) cho câu hỏi hiện tại kết hợp ngữ cảnh phù hợp.<br>4. Hệ thống sinh và hiển thị câu trả lời có căn cứ nguồn.<br>5. Phiên được cập nhật để phục vụ các câu hỏi tiếp theo. |
| **Luồng ngoại lệ** | Nếu ngữ cảnh trước không đủ để xác định nội dung người dùng đang hỏi tới → hệ thống yêu cầu người dùng làm rõ thay vì tự suy đoán. |
| **Điều kiện hậu quyết** | Người dùng nhận được câu trả lời tiếp nối đúng ngữ cảnh của phiên. |

---

### UC-F-04 — Giám sát / đánh giá độ chính xác hệ thống

| | |
|---|---|
| **Actor** | Admin, Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Theo dõi và đánh giá chất lượng câu trả lời của hệ thống dựa trên log và các phản hồi đã ghi nhận. |
| **Điều kiện tiên quyết** | Hệ thống đã có dữ liệu hỏi đáp/log hoặc phản hồi cần đánh giá. |
| **Luồng sự kiện chính** | 1. Admin/Chuyên gia phê duyệt chọn dữ liệu cần đánh giá.<br>2. Hệ thống hiển thị câu hỏi, câu trả lời, nguồn được sử dụng và phản hồi liên quan nếu có.<br>3. Người đánh giá đối chiếu kết quả với nội dung nguồn.<br>4. Kết quả đánh giá được ghi nhận để phục vụ theo dõi chất lượng hệ thống. |
| **Luồng ngoại lệ** | Nếu dữ liệu nguồn hoặc log liên quan không còn đầy đủ → hệ thống hiển thị rõ dữ liệu thiếu, không coi trường hợp đó là một đánh giá hoàn chỉnh. |
| **Điều kiện hậu quyết** | Kết quả đánh giá được lưu để phục vụ giám sát độ chính xác và rà soát các lỗi đã được báo cáo. |

---

### UC-G-01 — Quản lý tài khoản người dùng

| | |
|---|---|
| **Actor** | Admin |
| **Mô tả tóm tắt** | Tạo, cập nhật và khóa tài khoản người dùng của hệ thống. |
| **Điều kiện tiên quyết** | Admin đã đăng nhập và có quyền quản lý tài khoản. |
| **Luồng sự kiện chính** | 1. Admin mở danh sách tài khoản.<br>2. Xem/tìm kiếm tài khoản cần quản lý.<br>3. Admin tạo mới hoặc cập nhật thông tin tài khoản, hoặc khóa tài khoản khi cần.<br>4. Hệ thống kiểm tra dữ liệu và lưu thay đổi. |
| **Luồng ngoại lệ** | Nếu thông tin tài khoản không hợp lệ hoặc định danh đăng nhập bị trùng → hệ thống báo lỗi và không lưu. |
| **Điều kiện hậu quyết** | Thông tin và trạng thái tài khoản được cập nhật. |

---

### UC-G-02 — Quản lý vai trò (role)

| | |
|---|---|
| **Actor** | Admin |
| **Mô tả tóm tắt** | Quản lý các vai trò được sử dụng để phân quyền trong hệ thống. |
| **Điều kiện tiên quyết** | Admin đã đăng nhập và có quyền quản lý vai trò. |
| **Luồng sự kiện chính** | 1. Admin mở danh sách role.<br>2. Xem các role hiện có.<br>3. Admin tạo hoặc cập nhật role khi cần.<br>4. Hệ thống lưu thông tin role để sử dụng trong G-03. |
| **Luồng ngoại lệ** | Nếu role đang được sử dụng mà thao tác thay đổi làm cấu hình phân quyền không hợp lệ → hệ thống chặn thao tác và thông báo cho Admin. |
| **Điều kiện hậu quyết** | Danh sách role được cập nhật và sẵn sàng cho phân quyền. |

---

### UC-G-03 — Phân quyền theo chức năng (RBAC)

| | |
|---|---|
| **Actor** | Admin hệ thống |
| **Mô tả tóm tắt** | Gán quyền truy cập cụ thể cho từng role đối với các chức năng của hệ thống P-234. |
| **Điều kiện tiên quyết** | Đã định nghĩa danh sách role (G-02) và danh sách chức năng hệ thống. |
| **Luồng sự kiện chính** | 1. Admin hệ thống định nghĩa quyền cho từng role.<br>2. Admin gán role cho người dùng.<br>3. Hệ thống lưu cấu hình phân quyền.<br>4. Hệ thống áp dụng quyền cho các phiên đăng nhập của người dùng. |
| **Luồng ngoại lệ** | Nếu thao tác phân quyền không hợp lệ hoặc vượt quá quyền của tài khoản đang thực hiện → hệ thống chặn thao tác. |
| **Điều kiện hậu quyết** | Cấu hình phân quyền được cập nhật và áp dụng nhất quán cho người dùng trong hệ thống. |

---

### UC-G-04 — Xác thực và quản lý phiên đăng nhập

| | |
|---|---|
| **Actor** | Hệ thống |
| **Mô tả tóm tắt** | Xác thực người dùng và quản lý trạng thái phiên đăng nhập để kiểm soát truy cập hệ thống. |
| **Điều kiện tiên quyết** | Người dùng có tài khoản hợp lệ và chưa bị khóa. |
| **Luồng sự kiện chính** | 1. Người dùng gửi thông tin đăng nhập.<br>2. Hệ thống kiểm tra thông tin xác thực và trạng thái tài khoản.<br>3. Nếu hợp lệ, hệ thống tạo phiên đăng nhập và áp dụng role/quyền tương ứng.<br>4. Người dùng có thể đăng xuất; hệ thống kết thúc phiên.<br>5. Phiên hết hạn được hệ thống xử lý theo cấu hình. |
| **Luồng ngoại lệ** | Nếu thông tin xác thực sai hoặc tài khoản bị khóa → hệ thống từ chối đăng nhập. |
| **Điều kiện hậu quyết** | Người dùng có phiên hợp lệ để sử dụng các chức năng được cấp quyền, hoặc phiên được kết thúc khi đăng xuất/hết hạn. |

---

### UC-G-05 — Ghi log hoạt động người dùng

| | |
|---|---|
| **Actor** | Hệ thống |
| **Mô tả tóm tắt** | Ghi nhận các hoạt động quan trọng của người dùng để phục vụ truy vết và quản trị. |
| **Điều kiện tiên quyết** | Người dùng đang thực hiện một hoạt động thuộc phạm vi cần ghi log. |
| **Luồng sự kiện chính** | 1. Khi hoạt động cần theo dõi xảy ra, hệ thống ghi nhận người thực hiện, thời điểm, loại hành động và đối tượng liên quan.<br>2. Hệ thống lưu bản ghi log.<br>3. Admin có thể sử dụng log khi cần truy vết hoạt động. |
| **Luồng ngoại lệ** | Nếu việc ghi log gặp lỗi kỹ thuật → hệ thống ghi nhận lỗi vận hành để xử lý; không tự tạo dữ liệu log sai. |
| **Điều kiện hậu quyết** | Hoạt động người dùng được lưu lại để phục vụ truy vết. |

---

### UC-H-08 — Báo lỗi câu trả lời sai

| | |
|---|---|
| **Actor** | Người dùng, Chuyên gia phê duyệt |
| **Mô tả tóm tắt** | Cho phép người dùng gắn cờ khi phát hiện hệ thống đưa ra câu trả lời không chính xác, phục vụ cải thiện hệ thống về sau. |
| **Điều kiện tiên quyết** | Đã có câu trả lời của hệ thống cho một câu hỏi cụ thể. |
| **Luồng sự kiện chính** | 1. Người dùng chọn câu trả lời nghi ngờ sai.<br>2. Người dùng mô tả lý do cho rằng câu trả lời sai.<br>3. Hệ thống ghi nhận báo cáo lỗi, gắn với câu hỏi/câu trả lời liên quan, không tự động thay đổi câu trả lời.<br>4. Admin/Chuyên gia phê duyệt xem xét các báo cáo lỗi để đánh giá hệ thống. |
| **Luồng ngoại lệ** | Nếu không còn xác định được câu hỏi/câu trả lời gốc liên quan → hệ thống không ghi nhận phản hồi cho nội dung đó. |
| **Điều kiện hậu quyết** | Báo cáo lỗi được lưu trữ, phục vụ đánh giá độ chính xác hệ thống (F-04), không làm thay đổi câu trả lời đã sinh. |

---
