import PlaceholderDocument from "./PlaceholderDocument";
import Document from "./Document";

import { cookies } from "next/headers";

async function getAllDocuments() {
  const cookieStore = await cookies();
  const res = await fetch("http://127.0.0.1:8000/api/documents/all", {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

type DocumentType = {
    id: string,
    title: string,
    fileUrl: string,
    created_at: string,
    chat_id: string
}



const Documents = async() => {

    const documents = await getAllDocuments()

  return (
    <div className="flex flex-wrap p-5 bg-gray-100 max-sm:justify-center md:justfy-start rounded-sm gap-5 max-w-7xl mx-auto">
      <PlaceholderDocument />
      {
        documents.map((doc:DocumentType)=>(
          
          <Document key={doc.id} doc={{id:doc.id, title: doc.title, fileUrl: doc.fileUrl}}/>
        ))
      }
    </div>
  );
};

export default Documents;