import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import PdfView from "@/components/PdfView";
import Chat from "@/components/Chat";

const BACKEND_URL = "http://127.0.0.1:8000";

async function getDocument(doc_id: string) {
  const cookieStore = await cookies();
  const res = await fetch(`${BACKEND_URL}/api/documents/${doc_id}`, {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

async function getCurrentUser() {
  const cookieStore = await cookies();
  const res = await fetch(`${BACKEND_URL}/api/users/me`, {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

async function getMessages(doc_id: string) {
  const cookieStore = await cookies();
  const res = await fetch(`${BACKEND_URL}/api/chats/${doc_id}/get_messages`, {
    headers: { Cookie: cookieStore.toString() },
    cache: "no-store",
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.messages ?? [];   // unwrap the array from the response object
}

const Page = async ({ params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;

  const [file, messages, user] = await Promise.all([
    getDocument(id),
    getMessages(id),
    getCurrentUser(),
  ]);


  if (!file || !user) {
    redirect("/signin");
  }

  return (
    <div className="grid lg:grid-cols-6 min-h-0 h-full overflow-hidden bg-gray-100">
      <div className="col-span-6 lg:col-span-3 overflow-y-auto">
        <PdfView url={file.file_url} />
      </div>
      <div className="col-span-6 lg:col-span-3 min-h-0 overflow-y-auto border border-r-2">
        <Chat docId={id} initialMessages={messages} userName={user.username} />
      </div>
    </div>
  );
};

export default Page;