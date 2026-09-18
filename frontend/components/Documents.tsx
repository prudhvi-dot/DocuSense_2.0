import PlaceholderDocument from "./PlaceholderDocument";
import Document from "./Document";
import { cookies } from "next/headers";
import DocumentsList from "./DocumentsList";

async function getAllDocuments() {
  const start = performance.now();

  const cookieStore = await cookies();

  const res = await fetch(
    "http://127.0.0.1:8000/api/documents/all",
    {
      headers: {
        Cookie: cookieStore.toString(),
      },
      cache: "no-store",
    }
  );

  console.log(
    `getAllDocuments: ${(performance.now() - start).toFixed(0)}ms`
  );

  if (!res.ok) return [];

  return res.json();
}

export type DocumentType = {
  id: string;
  title: string;
  file_url: string;
  created_at: string;
  chat_id: string;
};

const Documents = async () => {
  const documents = await getAllDocuments();

  return (
    <div className="flex flex-wrap p-5 bg-gray-100 max-sm:justify-center md:justify-start rounded-sm gap-5 max-w-7xl mx-auto">
      <PlaceholderDocument />

      <DocumentsList documents={documents} />
    </div>
  );
};

export default Documents;