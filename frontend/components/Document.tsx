"use client"

import { useRouter } from "next/navigation";
import { File, Download, Trash2} from "lucide-react";

interface Doc {
    id: string;
    title: string;
    fileUrl: string;
}

const Document = ({ doc }: { doc: Doc }) => {
    const router = useRouter();

  return (
    <div
      key={doc.id}
      className="flex cursor-pointer flex-col items-center justify-between w-44 h-60 rounded bg-white  transition duration-300 drop-shadow-md text-gray-400"
    >
      <p onClick={() => router.push(`/dashboard/files/${doc.id}`)} className="hover:text-black text-sm">{doc.title}</p>
      <File onClick={() => router.push(`/dashboard/files/${doc.id}`)} className="h-12 w-12" />

      <div className="flex gap-1 justify-end p-2">       
        <Download onClick={() => window.open(doc.fileUrl, "_blank")} className="w-26 hover:text-black cursor-pointer"/>
      </div>
    </div>
  );
};

export default Document;