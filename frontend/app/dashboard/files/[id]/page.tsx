import { cookies } from "next/headers";
import PdfView from "@/components/PdfView";
import Chat from "@/components/Chat";

async function getDocument(doc_id: string) {
  const cookieStore = await cookies();
  const res = await fetch(`http://127.0.0.1:8000/api/documents/${doc_id}`, {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

const page = async ({ params }: { params: Promise<{ id: string }> }) => {
//   await auth.protect();

  const { id } = await params;

  const file = await getDocument(id)

  const url = file?.file_url;
  return (
    <div className="grid lg:grid-cols-6 h-full overflow-hidden bg-gray-100">
      <div className="col-span-6 lg:col-span-3 overflow-y-auto">
        <PdfView url={url as string} />
      </div>
      <div className="col-span-6 lg:col-span-3 overflow-y-auto border border-r-2">
        <Chat id={id} />
      </div>
    </div>
  );
};

export default page;