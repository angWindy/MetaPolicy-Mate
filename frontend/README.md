# P234 RAG - MVP Frontend

Frontend cho hệ thống tra cứu văn bản P234, xây dựng với Next.js.

## Tính năng

- **Trang Chatbot**: Tra cứu thông tin với citation references (như ChatGPT/NotebookLM)
- **Trang Quản lý Tài liệu**: Upload, duyệt, và xuất bản tài liệu

## Yêu cầu

- Node.js >= 18
- Backend FastAPI đang chạy tại `http://localhost:8000`

## Cài đặt

```bash
# Cài đặt dependencies
npm install

# Copy file môi trường
cp .env.example .env.local

# Chạy development server
npm run dev
```

## Cấu hình

Chỉnh sửa `.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## Cấu trúc thư mục

```
frontend/
├── src/
│   ├── app/              # Next.js App Router
│   │   ├── (main)/       # Layout với sidebar
│   │   │   ├── chat/     # Trang chatbot
│   │   │   ├── documents/# Trang quản lý tài liệu
│   │   │   └── page.tsx  # Trang chủ
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/       # React components
│   │   ├── MainLayout.tsx
│   │   └── Sidebar.tsx
│   └── lib/              # Utilities
│       ├── api.ts        # API client
│       └── types.ts     # TypeScript types
├── public/
└── package.json
```

## Chạy ứng dụng

1. Chạy backend (FastAPI):
```bash
cd /home/angwindy/Dev/Vin/P-234
source ~/miniconda3/etc/profile.d/conda.sh
conda activate p234
uvicorn src.main:app --reload --port 8000
```

2. Chạy frontend (Next.js):
```bash
cd frontend
npm run dev
```

3. Truy cập: http://localhost:3000

## Scripts

- `npm run dev` - Development server
- `npm run build` - Production build
- `npm run start` - Production server
- `npm run lint` - ESLint
