"use client"

import { useRouter } from "next/navigation";
import { File, Download, Trash2, Loader2Icon} from "lucide-react";
import { useEffect, useState } from "react";

type Doc = {
  id: string;
  title: string;
  fileUrl: string;
};

type DocumentProps = {
  doc: Doc;
  onDelete: (doc_id: string) => void;
  isDeleting: boolean
};



const Document = ({ doc, onDelete, isDeleting }: DocumentProps) => {
    const router = useRouter();

  return (
    <div
      key={doc.id}
      className="flex cursor-pointer flex-col items-center justify-between w-44 h-60 rounded bg-white  transition duration-300 drop-shadow-md text-gray-400"
    >
      <p onClick={() => router.push(`/dashboard/files/${doc.id}`)} className="hover:text-black text-sm">{doc.title}</p>
      <File onClick={() => router.push(`/dashboard/files/${doc.id}`)} className="h-12 w-12" />

      <div className="flex gap-1 justify-end p-2">  

        {isDeleting ? (
    <Loader2Icon className="animate-spin" />
  ) : (
    <Trash2 onClick={()=>{
          onDelete(doc.id)
        }} className="w-26 hover:text-black cursor-pointer"/>   
  )} 
        
        <Download
  onClick={() => {
    const downloadUrl = doc.fileUrl.replace(
      "/upload/",
      "/upload/fl_attachment/"
    );

    window.open(downloadUrl, "_blank");
  }}
  className="w-26 hover:text-black cursor-pointer"
/>
      </div>
    </div>
  );
};

export default Document;