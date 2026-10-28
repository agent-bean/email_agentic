# Tham khảo: tri thức từ bộ giáo trình

Bản tổng hợp nguồn trích ngày 28/10/2026. Đây là tài liệu tham khảo từ giáo trình, notebook và code mẫu cục bộ, không phải kiến trúc được chọn hoặc danh mục tài nguyên đã được cấp cho dự án. Các mục “Áp dụng” là suy luận phục vụ triển khai Email Assistant, không tự động trở thành yêu cầu đã chốt. Căn cứ phạm vi nằm trong [PRD](../project-overview-pdr.md). Mã Sxx dẫn tới danh mục nguồn riêng (chỉ lưu local), để mở tài liệu gốc.

Các nhận xét về thư viện, model, giao thức và cấu hình mô tả **nội dung bộ tài liệu**, không khẳng định đây là phiên bản hiện hành hoặc cấu hình phù hợp production. Chưa kiểm chứng API bằng cách chạy ứng dụng.

## 1. Agent và Harness Engineering

**Nguồn:** S01, S30, S28.

- Agent tương tác với môi trường, thực hiện hành động và nhận observation để tiến tới mục tiêu. Email, web, lịch và DB là môi trường số của dự án.
- Tài liệu phân biệt LLM sinh nội dung, chatbot hội thoại và agent thực thi nhiệm vụ nhiều bước. Bảng so sánh mang tính giảng dạy, không nên coi là định nghĩa tuyệt đối cho mọi sản phẩm.
- **ReAct:** lặp quan sát/lập luận, chọn hành động, gọi tool, nhận kết quả, tiếp tục hoặc kết thúc. Quan trọng khi kiểm tra là hành động/tool/kết quả, không yêu cầu model công khai suy luận nội bộ.
- Các kỹ thuật planning được giới thiệu gồm Chain-of-Thought, self-reflection và subgoal decomposition.
- S01 minh họa coding agent: sinh code, chạy sandbox, kiểm exit code/stdout/stderr, sửa lỗi hoặc tiếp tục bước sau, dừng theo giới hạn iteration.
- Ví dụ Docker trong S01 trang 12–13 cho agent gọi Docker daemon qua socket để lấy log sandbox. Đây là kiến thức của coding agent, không phải yêu cầu cấp Docker socket cho Email Assistant.
- **Agent = Model + Harness:** tăng độ tin cậy bằng môi trường, luồng thực thi và cơ chế kiểm soát quanh model thay vì chỉ đổi prompt/model hoặc huấn luyện lại.
- **Ratchet:** mỗi lỗi dẫn tới bài học, kiểm soát và kiểm thử để giảm tái phạm. Đây là nguyên tắc cải tiến, không phải đảm bảo toán học rằng chất lượng luôn tăng.
- Ví dụ dùng nhầm văn bản cũ trong S30: bổ sung instruction, lọc retrieval theo hiệu lực/phê duyệt/phiên bản, validation trước trả lời và reviewer kiểm nguồn. Áp dụng cho dự án bằng nguồn doanh nghiệp/tin tức có xuất xứ và thời điểm, thay vì dùng nguyên quy tắc pháp lý của ví dụ.

### Bảy lớp harness của giáo trình

| Harness | Câu hỏi giải quyết | Liên hệ Email Assistant |
|---|---|---|
| Context | Đưa đúng thông tin nào vào ngữ cảnh? | Email, hồ sơ doanh nghiệp, lịch, kết quả web và memory. |
| Tool | Agent gọi công cụ như thế nào? | Registry/gateway, schema, auth, scopes, rate limit, audit, execute. |
| Orchestration | Các bước/agent phối hợp thế nào? | Tách nhánh nghiên cứu, ghép kết quả, dừng chờ người duyệt. |
| Evaluation | Agent làm đúng và đủ không? | Sáu case, chất lượng briefing, regression. |
| AgentOps | Hệ thống đang chạy thế nào và lỗi ở đâu? | Metrics request/tool, chi phí, latency, trace/span, Grafana. |
| Security | Ngăn truy cập và hành động trái phép ra sao? | Injection, quyền dữ liệu, bảo vệ secret. |
| Governance | Ai được quyết định, ai chịu trách nhiệm? | Người duyệt, policy và bằng chứng quyết định. |

Nguồn bảng: S30 trang 11–12. Không có yêu cầu dự án phải triển khai chứng nhận hay toàn bộ chương trình governance doanh nghiệp chỉ vì giáo trình có lớp này.

## 2. Tool Harness, xác thực và phân quyền

**Nguồn:** S43, S44, S45, S46.

Tool Harness quản lý việc khám phá, chọn, thực thi tool, xử lý lỗi và trả kết quả có cấu trúc. Tool Registry là catalog tên tool, mô tả, schema, quyền và handler. Giáo trình yêu cầu lời gọi đi qua gateway thay vì cho LLM gọi thẳng dịch vụ.

| Cơ chế | Tri thức cần giữ | Liên hệ dự án |
|---|---|---|
| Schema validation | Kiểm tool có tồn tại, trường bắt buộc, kiểu, giá trị hợp lệ và trường dư. | Email recipient, nội dung, ID lịch, tên công ty không được bỏ qua validation. |
| Authentication | Xác thực danh tính gọi hoặc danh tính tích hợp dịch vụ. | Tài khoản dùng ứng dụng và credential gọi Gmail/Calendar có thể là hai lớp khác nhau. |
| Authorization/scopes | Danh tính hợp lệ chỉ được làm các thao tác được cấp. | Quyền đọc email/lịch tách với gửi email và ghi KB. |
| Rate limit | Giới hạn số lời gọi trong cửa sổ thời gian theo danh tính/phạm vi. | Hạn chế gọi tool/API lặp và chi phí phát sinh. |
| Audit | Ghi người gọi, role, tool, tham số đã làm sạch, kết quả, thời gian và trạng thái. | Có request ID để nối với trace; không lưu token hoặc API key vào log. |
| Execute | Handler thực hiện nghiệp vụ sau các kiểm tra. | Không coi JSON tool call do model tạo ra là hành động đã được cho phép. |

### Các khái niệm auth trong giáo trình

- **API key:** secret dùng nhận diện ứng dụng. Khả năng scope, hết hạn và rotate tùy dịch vụ; bảng slide đơn giản hóa, không đủ để kết luận mọi API key đều không có scope.
- **OAuth2:** cơ chế ủy quyền để ứng dụng truy cập tài nguyên thay người dùng. Tài liệu mô tả authorization, đổi code lấy token ở backend, gọi API và refresh token.
- **Bearer:** cách truyền token qua header `Authorization: Bearer …`; không phải một loại danh tính hay đồng nghĩa với JWT.
- **Service account:** danh tính máy/dịch vụ cho tác vụ nền. Không tự suy ra service account có quyền truy cập hộp thư/lịch cá nhân.
- **RBAC:** gán quyền theo role. **ABAC:** xét thuộc tính như bộ phận, thời gian hoặc tài nguyên. **ACL:** quyền trực tiếp trên tài nguyên.
- **Least privilege:** mỗi agent chỉ có quyền tối thiểu cần cho nhiệm vụ.

S44 có ba script minh họa Bearer token, OAuth2 Drive và service account. Đây là ví dụ auth, chưa phải tích hợp Gmail/Calendar hoàn chỉnh của đề.

### Retry và kết quả tool

S43 trang 34 phân biệt lỗi tạm thời (timeout, mạng, 429, 503) với lỗi tham số/quyền/tài nguyên (400, 401, 403, 404). Retry có backoff phù hợp nhóm tạm thời, không lặp vô hạn lỗi quyền hoặc input. Với gửi email, cần xử lý kết quả không chắc chắn để tránh gửi trùng khi retry; điểm này là suy luận triển khai, chưa có trong đề.

**Sai khác cần biết giữa hình và code S45:** hình yêu cầu audit trước execute. `registry.py::ToolRegistry.call` trong ZIP thực tế gọi execute rồi mới audit kết quả thành công. Nhánh lỗi chỉ audit khi đã xác thực được user, nên chưa bao phủ lỗi schema/auth ban đầu. `validate_schema` minh họa kiểm required/type/enum, chưa phải bộ validator đầy đủ mọi JSON Schema. Rate limiter dùng danh sách timestamp theo cửa sổ trượt dù docstring gọi “token bucket”. Không lấy tên/comment làm bằng chứng đã đáp ứng toàn bộ yêu cầu.

### MCP và A2A

MCP chuẩn hóa kết nối agent với tool/dữ liệu, có mô tả và khám phá tool. API vẫn là giao diện dịch vụ phía sau. MCP không tự thay thế policy, scope, audit hoặc phê duyệt. S46 minh họa MCP server/client và agent gọi qua registry.

A2A tập trung trao đổi tác vụ giữa các agent. S34 trang 7–8 so sánh A2A với MCP. Multi-agent không mặc nhiên cần hai giao thức này; đề Email Assistant không bắt buộc MCP/A2A.

## 3. Context, RAG và memory

**Nguồn:** S14, S12, S13, S15, S17, S16, S32, S39.

### Luồng RAG

1. Đọc và chuẩn hóa tài liệu.
2. Chia chunk theo chiến lược phù hợp.
3. Tạo embedding, lưu vector và metadata.
4. Nhận query, truy xuất thông tin liên quan.
5. Có thể lọc metadata, hybrid search hoặc rerank.
6. Đưa context đã truy xuất cùng yêu cầu vào LLM để tạo kết quả có căn cứ.

RAG có bước retrieval trước generation, không nhất thiết phải dùng vector DB. Keyword/BM25 cũng là hướng retrieval trong giáo trình. Với Company Info, truy vấn DB có cấu trúc vẫn có thể phù hợp hơn embedding.

### Chunking và truy xuất

| Kỹ thuật | Nội dung giáo trình | Trade-off liên quan |
|---|---|---|
| Character splitting | Chia cố định theo độ dài. | Đơn giản, dễ cắt mất ý. |
| Recursive splitting | Thử đoạn, dòng, câu, rồi ký tự khi còn quá dài. | Giữ cấu trúc tương đối tốt; không bảo đảm hiểu ngữ nghĩa hoàn toàn. |
| Document specific | Chia theo cấu trúc loại tài liệu. | Phù hợp hồ sơ doanh nghiệp có tiêu đề/bảng. |
| Semantic chunking | Dùng embedding phát hiện chuyển chủ đề. | Tăng chi phí nhưng có thể giữ nhóm ý. |
| LLM chunking | Dùng LLM quyết định ghép/chia theo tiêu đề và tóm tắt. | Cần đánh giá chi phí và tính ổn định. |
| Agentic chunking | Planner, execution và validation phối hợp. | Là kiến thức nâng cao, không bắt buộc cho đề. |
| Metadata filtering | Giới hạn phạm vi trước truy xuất. | Có thể lọc theo công ty, nguồn, ngày và quyền truy cập. |
| Reranking | Sắp lại kết quả theo độ liên quan với query. | Đổi thêm chi phí lấy chất lượng retrieval. |
| Parent-child/hierarchical | Tìm đoạn nhỏ, lấy ngữ cảnh lớn hơn hoặc đi theo phân cấp. | Giữ phần giải thích khi chunk nhỏ thiếu ngữ cảnh. |
| Hybrid search | Kết hợp keyword và semantic. | Giữ tên riêng/domain/mã chính xác đồng thời tìm theo ý nghĩa. |
| Context compression/reorder | Nén hoặc sắp ngữ cảnh trước generation. | Có nguy cơ mất chi tiết; cần đo thay vì mặc định dùng. |

S14 nêu các lựa chọn vector storage như Qdrant, ChromaDB, MongoDB Atlas, Elasticsearch, Supabase và embedding như bge-m3/OpenAI. Đây là ví dụ công nghệ, chưa chọn cho dự án. Giới hạn token và kích thước vector phải theo model được chọn, không dùng một số chung từ slide.

### Memory

- **Short-term:** trạng thái/ngữ cảnh của phiên hoặc lần chạy, bị giới hạn context window.
- **Long-term:** thông tin lưu qua nhiều lần chạy trong DB/vector/graph hoặc kho khác.
- S12 phân biệt sáu loại: fact, preference, context, episodic, procedural và summary. Phân loại giúp xác định nội dung cần giữ và cách tìm lại.
- Bảy nhóm nén ngữ cảnh trong S12: summarization, semantic compression, deduplication, hierarchical memory, knowledge graph compression, context distillation và latent compression.
- Summarization giảm token nhưng có thể mất chi tiết hoặc tích lũy sai lệch. Dedup cần tránh gộp nhầm hai pháp nhân. Distillation giữ mục tiêu/fact/ràng buộc nhưng có thể bỏ sót thông tin. Latent compression là kiến thức nâng cao trong tài liệu, chưa có yêu cầu triển khai.
- Áp dụng: giữ hồ sơ công ty và lịch sử nghiên cứu, đồng thời phân biệt fact có nguồn với suy luận nhu cầu tiềm năng. Báo cáo cũ không mặc nhiên là nguồn đúng hoặc còn mới.

S32 `memory/manager.py` có Qdrant + BM25, ghép thứ hạng bằng Reciprocal Rank Fusion, store Q/A và ingest chunk. BM25/cache nằm trong bộ nhớ của instance; đoạn đã đọc không thể hiện cơ chế phục hồi BM25 từ Qdrant sau restart. Không coi đây là toàn bộ chức năng memory bền vững mà đề yêu cầu.

### Graph RAG

**Nguồn:** S11, S14.

- Chuẩn hóa tài liệu thành entity và relationship để truy vấn quan hệ.
- Tài liệu S11 trình bày ba hướng cần phân biệt: sinh Cypher trên graph, học graph embedding bằng GCN/graph autoencoder và GraphRAG dùng community summary.
- Cypher phù hợp truy vấn có cấu trúc nhưng có thể sinh sai truy vấn khi thiếu schema/mẫu.
- Graph embedding kết hợp thông tin lân cận, truy vấn entity gần rồi duyệt quan hệ.
- Community GraphRAG: chia chunk, trích entity/relationship, hợp nhất graph, chia community bằng Leiden, tóm tắt community, trả lời từng phần rồi tổng hợp.
- Lợi ích: quan hệ rõ, multi-hop, giải thích đường dẫn dữ liệu. Chi phí: entity resolution, thiết kế graph, ingestion, cập nhật và bảo trì.
- S11 trang 3 lưu ý nội dung mang tính thử nghiệm. Email Assistant có quan hệ người liên hệ–công ty–cuộc họp, nhưng đề không bắt buộc graph DB, GCN hoặc GraphRAG. Chỉ áp dụng khi nhu cầu truy vấn và đánh giá chứng minh cần.

## 4. Orchestration và multi-agent

**Nguồn:** S35, S34, S36, S37, S38, S39.

Orchestration gồm planning, workflow, state, routing, execution và recovery. Một workflow cần biết nhiệm vụ nào phụ thuộc nhau, state nào truyền giữa các bước, lỗi dẫn tới retry/fallback/dừng hay cần người xử lý.

| Pattern | Điểm mạnh | Hạn chế |
|---|---|---|
| Sequential | Luồng rõ, dễ theo dõi phụ thuộc. | Latency cộng dồn, lỗi đầu có thể chặn bước sau. |
| Parallel | Giảm thời gian cho các tác vụ độc lập. | Cần đồng bộ kết quả và quản lý lỗi từng nhánh. |
| Hierarchical | Manager phân việc cho agent chuyên môn. | Manager có thể thành bottleneck hoặc điểm quyết định sai. |
| Debate | Có phản biện giữa các agent. | Tốn token/thời gian, cần điều kiện dừng. |
| Voting | Kết hợp nhiều đánh giá. | Đa số không bảo đảm đúng. |
| Swarm | Linh hoạt khi các agent giao tiếp phân tán. | Khó kiểm soát và debug, giao tiếp dư thừa. |

Áp dụng trực tiếp nhất từ sơ đồ đề: Email phân tích trước; Research/Calendar/Company Info có thể chạy song song; Memory hợp nhất rồi Report; cuối cùng dừng chờ phê duyệt trước xuất bản. Cần tránh tự thêm các agent thứ tám/chín chỉ để dùng đủ pattern của khóa học.

### State, DAG và LangGraph

- DAG mô tả task và quan hệ phụ thuộc có hướng, không chu trình. Agent loop có retry/quay lại không phải một DAG thuần.
- State machine dùng trạng thái và điều kiện chuyển tiếp để kiểm soát workflow.
- Routing có thể dựa rule, LLM, semantic hoặc kết hợp. Agent chuyên biệt có thể dùng chung LLM nhưng khác prompt, tool, quyền, memory và nhiệm vụ.
- Trong ví dụ LangGraph: state là dữ liệu chung, node là hàm đọc/cập nhật state, edge là chuyển tiếp cố định hoặc có điều kiện, StateGraph kết hợp thành workflow.
- S36 notebook thời tiết minh họa vòng model–tools và điều kiện kết thúc. Nó không phải ứng dụng multi-agent Email Assistant.
- S39 `agent/core.py` xây graph `retrieve_memory → reason`, rẽ sang `tools → reason` hoặc `save_memory → END`. Đây là graph một agent với tool loop, chưa tự đáp ứng bảy vai trò của đề.
- S35 nhắc checkpointing/HITL/streaming như khả năng framework. Chưa có bằng chứng mọi khả năng đó đã được cài trong các ZIP mẫu.

## 5. Evaluation: đúng kết quả và đúng quá trình

**Nguồn:** S21, S23, S22.

Golden dataset gồm đầu vào/nhiệm vụ, expected output hoặc ground truth, và cách chấm. Cần bao phủ tác vụ dễ, nhiều bước, tool use, thiếu thông tin và edge case. Sáu case của đề là khung đầu tiên, chưa phải dataset đầy đủ.

- **Task success:** hoàn thành mục tiêu cuối cùng.
- **Trajectory evaluation:** xem chuỗi hành động/tool, tính đúng, hiệu quả, lỗi lan truyền và kết quả cuối. Giúp tìm bước gây thất bại.
- **LLM-as-a-judge:** dùng model chấm theo tiêu chí/rubric. Không thay thế dữ liệu chuẩn hoặc kiểm tra nguồn.
- **Human evaluation:** ghi phản hồi, phân loại lỗi như hallucination, thiếu thông tin, logic, định dạng.
- **A/B:** so phiên bản model/prompt/workflow trên cùng tập đánh giá.
- **Regression:** chạy lại dataset sau thay đổi model, prompt, embedding, dữ liệu hoặc tool.

### Tách các tầng chất lượng

| Tầng | Metric/tiêu chí trong giáo trình | Ý nghĩa với dự án |
|---|---|---|
| Retrieval | Hit@K, Recall@K | Tìm được đúng hồ sơ/nguồn và bao phủ thông tin cần thiết. |
| Ranking | MRR, MAP, nDCG@K | Nguồn hữu ích có được xếp lên trên hay không. |
| Context | Precision, recall, entities recall, relevance | Context chứa thông tin cần và tránh dữ liệu lạc đề. |
| Generation | Correctness, faithfulness/groundedness, relevancy, instruction following | Briefing đúng, có căn cứ, phù hợp email/cuộc họp và format. |
| Robustness | Noise sensitivity, hallucination | Không biến nguồn nhiễu thành kết luận sai. |
| Operations | Latency, cost | Có thể so chất lượng với thời gian và chi phí. |
| Agent | Tool selection, argument accuracy, task success | Đúng tool, đúng tham số, đúng kết quả nghiệp vụ. |

Hit@K kiểm có ít nhất một kết quả đúng trong top K. Recall@K là số mục liên quan đã tìm thấy chia tổng mục liên quan. Hai chỉ số chỉ trùng trong trường hợp mỗi query có một mục đúng.

S23 còn giải thích Exact Match, String Presence, BLEU, ROUGE và n-gram. Chúng hữu ích cho trường dữ liệu hoặc nội dung có cấu trúc nhưng không tự đo tính đúng của báo cáo mở. Một briefing có thể diễn đạt khác reference mà vẫn đúng; có thể trùng từ mà vẫn sai sự thật.

### Lỗi/điểm không nhất quán trong slide đánh giá

- S23 trang 22 ghi `4 / 6 = 0.5`; phép chia đúng là khoảng **0.667**.
- S23 trang 7 nói Recall@K dùng nhiều document đúng nhưng có dòng “Ground truth is 1 relevant document per query”, không nhất quán với ví dụ trang 8.
- S23 trang 23–24 có nhãn Context Relevance/Recall bị dùng lẫn.
- S23 trang 32 cột Precision lại ghi “Recall” trong công thức. Phải đối chiếu mẫu số trước khi đưa vào evaluator.

Không sao chép nguyên các lỗi này thành công thức hoặc contract dự án. Các cách chấm LLM và ví dụ đơn giản trong giáo trình cũng chưa xác định chính xác phiên bản metric của một thư viện cụ thể.

### Kiến thức benchmark

S21 giới thiệu GAIA, SWE-bench, WebArena/BrowserArena, ToolBench, τ-bench, AgentBench, BFCL và MINT để phân biệt đánh giá agent tổng quát, coding, browser và tool calling. Đây là tài liệu tham khảo, không thay thế sáu case nghiệp vụ.

S22 giới thiệu MMLU, GLUE, TruthfulQA, GSM8K, HellaSwag, HumanEval, MATH, IFEval, pass@k, đánh giá tự động và con người. Với pass@k, ý nghĩa là khả năng có ít nhất một mẫu đúng trong k mẫu; không dùng trực tiếp làm “tỷ lệ email xử lý đúng”. Các số liệu SOTA/model trong slide không được xác minh lại tại thời điểm trích.

## 6. Security và Governance

**Nguồn:** S41, S27, S28.

### Ranh giới tin cậy

Nội dung email, attachment, web và tool result là dữ liệu cần đọc, không có quyền tự ghi đè instruction, cấp scope hoặc tạo approval. Đây là cách áp dụng phân tách untrusted input và system prompt trong S41 trang 7 cho đúng bề mặt dự án.

Phòng thủ trong giáo trình gồm prompt filter, permission engine, least privilege, kiểm quyền dữ liệu, human confirmation và secret manager. Việc tách role/message hỗ trợ cô lập dữ liệu nhưng không tự bảo đảm chống mọi prompt injection.

S41 giới thiệu jailbreak qua nhập vai/persona, kịch bản hư cấu, đa ngôn ngữ/mã hóa và tâm lý ngược. Bộ lọc từ khóa đơn lẻ có thể bỏ sót biến thể; giáo trình khuyến nghị phòng thủ nhiều lớp, kiểm intent, policy và đầu ra.

### Dữ liệu và secret

- Phân biệt quyền gọi tool với quyền đọc từng tài nguyên/record.
- PII trong giáo trình gồm định danh, điện thoại, email, mã số thuế, địa chỉ. Phát hiện/che khi phù hợp và ghi access.
- Không đưa key/token vào prompt, báo cáo, log hoặc mã nguồn. S41 phân biệt mã hóa lưu trữ bằng KMS với secret manager có xác thực, quyền, TTL/rotation và audit truy cập.
- Ví dụ DB/secret trong slide không phải credential được cấp cho dự án.

### Phê duyệt và trách nhiệm

- Approval workflow quyết định một action có được thực hiện không. HITL rộng hơn, gồm review, chỉnh sửa, từ chối, override, escalation.
- S27 minh họa pending action: tạo đề nghị trước, chỉ execute sau khi có approval hợp lệ.
- Cần biết hành động nào, thời điểm nào, ai được duyệt, bằng chứng gì cho người duyệt và audit quyết định ra sao.
- Explainability lưu decision, evidence thực đã truy xuất, policy/rule, thời gian và model. Không để LLM tự chế bằng chứng sau khi đã kết luận.
- Giáo trình nêu risk về accuracy, privacy, security, bias, operational, legal và financial, cùng ISO/IEC 42001, NIST AI RMF và EU AI Act. Đây là kiến thức, không phải yêu cầu pháp lý/chứng nhận đã xác lập cho dự án.

## 7. AgentOps và cấu hình tham khảo

**Nguồn:** S05, S06, S07.

- Monitoring nhìn tổng thể health, lượng request, lỗi, latency, cost. Tracing nhìn sâu từng request qua các operation/span.
- Telemetry có thể thu token, latency, tool call, retrieval, model/version, lỗi và điểm đánh giá. Dữ liệu nhạy cảm cần được làm sạch trước khi lưu.
- Observability trong giáo trình kết hợp logs, metrics, traces và evaluations.
- Cost tracking cần phân rã embedding/retrieval/LLM/tool nếu có tính phí; không suy ra tổng chi phí từ một span LLM duy nhất.
- Tối ưu latency: chạy nhánh độc lập song song, caching, model routing, prompt compression, streaming, giảm bước không cần thiết. Cần đo trước/sau.
- Drift có thể đến từ user behavior, data, model, prompt và API/tool thay đổi. Baseline/evaluation giúp phát hiện suy giảm.
- S05 liệt kê LangSmith, OpenTelemetry, Phoenix và Datadog như công cụ tham khảo. Đề vẫn yêu cầu dashboard Grafana.

### Stack hiện hữu trong S06

Đọc `Assignemnt-1/docker-compose.yml`, `telemetry.py` và cấu hình trong `observability/` cho thấy:

| Thành phần | Vai trò trong mẫu | Port ghi trong mẫu |
|---|---|---|
| OpenTelemetry Collector | Nhận OTLP HTTP, chuyển trace/metrics | Host 4318 |
| Tempo | Lưu và truy vấn trace | Host HTTP 3200; OTLP gRPC nội bộ 4317 |
| Prometheus | Scrape metrics từ Collector | Host 9090; scrape Collector nội bộ 8889 |
| Grafana | Dashboard, nguồn Prometheus và Tempo | Host 3000 |

`telemetry.py` có agent run counter, LLM call/input/output token counter, latency histogram, cost counter và tool call/error/latency. FastAPI instrumentation và các span là điểm tham khảo để nối cả request. Chưa chạy stack để xác nhận dashboard/chi phí chính xác.

Các port này là cấu hình mẫu, chưa là quyết định port dự án. Compose mẫu bật anonymous Admin và tắt login Grafana; cần thiết kế lại quyền truy cập khi đưa demo ra ngoài. Đây là giới hạn quan sát từ source, không phải đã xảy ra lộ dữ liệu.

## 8. Bản đồ code mẫu và mức tái sử dụng

Đường dẫn trong bảng là **bên trong ZIP**, không phải file đã cài trong repo. Chưa thực thi hoặc chứng nhận chất lượng các ví dụ.

| Nguồn | File/module đáng đọc | Tri thức có thể dùng | Giới hạn khi áp dụng |
|---|---|---|---|
| S02 code-agent | `planner.py`, `executor.py`, `agent.py`, `schemas.py`, Dockerfiles | Planner/executor, sandbox, vòng sửa lỗi | Bài coding agent, không phải hệ thống email. |
| S03 mini-agent | `react/loop.py`, `parser.py`, `trace.py`, `tools/base.py` | Vòng ReAct, parse action, tool abstraction, trace | Demo công cụ số học. |
| S09 Assignment TODO | `registry/registry.py`, `services/*`, `tools/*` | Bố cục registry, đọc file, Drive, memory | Registry có TODO tại schema/auth/scope/rate/audit/execute và pipeline. |
| S44 auth practice | `bearer-token-demo.py`, `oauth2-drive-demo.py`, `service-account-demo.py` | Ba cơ chế auth | Demo Drive/auth; không tự đủ auth email/lịch. |
| S45 tool registry | `registry.py`, `tools.py`, `demo.py`, `llm_agent.py` | Sáu bước và case thành công/lỗi | User DB/rate/audit trong RAM, các tool demo, sai khác audit đã nêu. |
| S46 MCP demo | `mcp_server.py`, `mcp_client_demo.py`, `llm_mcp_agent.py`, `registry.py` | MCP discovery/call và ghép agent–registry | Cần xem lại cách thực thi policy trước tái sử dụng. |
| S16 RAG demo | `backend/services/chunking.py`, `embedding.py`, `vectorstore.py`, routers ingest/chat | FastAPI, upload, chunk, embedding, Qdrant, giao diện chat/upload | Demo RAG, chưa làm 7 agent và approval. |
| S32 openminiclaw | `openclaw/tools/gmail.py`, `calendar.py`, `crm.py`, `google_auth.py`, `memory/*`, `reasoning/*` | Gmail/Calendar, auth, ReAct/ToT/debate, hybrid memory | `MockCRM` dùng dữ liệu mẫu; Gmail send dùng `MIMEText`, chưa có attachment. |
| S39 LangGraph OpenMiniClaw | `openclaw/agent/core.py`, `schema.py`, tools, memory | StateGraph, tool loop, memory trước/sau | Chưa là 7 agent Email Assistant, chưa chứng minh approval. |
| S37 multi-agents demo | `src/agents/*`, `crew/*`, `a2a/*`, `tools/*` | Chuyên môn hóa, orchestration, ví dụ A2A | Bài CSKH hàng không, tool/data mô phỏng. README mô tả kiến trúc, chưa xác nhận triển khai phân tán. |
| S38 CrewAI | `src/crew/customer_service_flow.py`, gatherer/decision/executor | Flow nhiều crew trong process, thu thập rồi quyết định/thực thi | Bài CSKH hàng không, không mang nguyên nghiệp vụ refund/flight sang dự án. |
| S06 AgentOps | `telemetry.py`, `agent.py`, `registry/registry.py`, `observability/*` | Gắn telemetry, dashboard, trace và metric | Cần bổ sung/kiểm chứng bảy agent và chỉ số theo request của đề. |
| S07 Docker assignment | `Dockerfile`, `docker-compose.yml`, `server.py`, services/tools | Đóng gói ứng dụng và dịch vụ liên quan | Không đồng nghĩa deploy email demo đã hoàn tất. |
| S15 ingestion notebook | Cell embeddings, tạo collection, point ID, payload, upsert | Ingest Qdrant, schema vector và dữ liệu | Có thao tác ghi/khởi tạo collection, không chạy trên DB đang dùng khi chưa đánh giá và backup. |
| S17 search notebook | Cell embedding, vector search, context, chat | Retrieval rồi generation | Mẫu notebook, chưa thành service có policy/approval. |
| S36 LangGraph notebook | `AgentState`, tool thời tiết, model/tools node, routing | Tool loop và state | Dùng bài thời tiết, không đáp ứng nguyên đề email. |

S32 `GmailTool._send` gửi email trực tiếp qua Gmail API và trả message ID/thread ID. Cần ghép ranh giới approval và hỗ trợ attachment theo đề, không coi chỉ đổi prompt là đủ. S32/S39 còn có tool tạo/sửa/xóa lịch và sửa trạng thái email; những quyền này vượt quá nhu cầu đọc lịch cơ bản, không phải chức năng bắt buộc của đề.

Một số ZIP có `.env` hoặc `token.json`. Chỉ ghi nhận sự hiện diện từ inventory, không đọc hoặc sử dụng nội dung. Không giải nén nguyên bộ vào repo rồi commit.

## 9. Demo và cách đọc bộ tài liệu

**Nguồn:** S19, S25, S28.

S19 gợi ý thể hiện mục tiêu, kiến trúc, luồng xử lý, LLM, đọc file/chunk/embedding, tools, MCP nếu dùng, memory, khó khăn và hướng cải thiện. Demo nên bao phủ use case và có log/workflow/tracing minh họa hành động.

Tuy nhiên S19 mang tên AI Drive Agent, còn S28 là Fulfillment Agent xử lý đơn hàng/kho/vận chuyển. Chỉ tái sử dụng cách giải thích harness và trình bày kiến trúc. Không mang các yêu cầu Drive, OMS/WMS/ERP/TMS, hủy đơn hoặc thanh toán vào scope Email Assistant.

Thứ tự đọc để triển khai: đề S25; Tool S43/S45; Orchestration S34/S35; RAG/Memory S14/S12; Security/Governance S41/S27; Evaluation S21/S23; AgentOps S05/S06. Dùng code S32/S39 tham khảo tích hợp email/lịch, S37/S38 tham khảo chia vai trò, rồi đối chiếu lại từng yêu cầu.

## 10. Giới hạn kiểm chứng

Code/notebook được đọc tĩnh, chưa kiểm thử dependency, credential, runtime hoặc truy cập dịch vụ. Các liên kết ngoài trong đề chưa được đọc. Khi một chi tiết quyết định thiết kế, đối chiếu tài liệu gốc; bản tổng hợp không thay thế việc kiểm chứng tích hợp thực tế.
