"use client";

import Document from "./Document";
import { DocumentType } from "./Documents";
import { useState } from "react";

type Props = {
  documents: DocumentType[];
};

const DocumentsList = ({ documents: initialDocuments }: Props) => {
  const [documents, setDocuments] = useState(initialDocuments);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const deleteFile = async (doc_id: string) => {
  try {
    setDeletingId(doc_id);

    const res = await fetch(`/api/backend/documents/${doc_id}`, {
      method: "DELETE",
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error("Failed to delete document");
    }

    setDocuments((prev) =>
      prev.filter((doc) => doc.id !== doc_id)
    );
  } catch (error) {
    console.error("Something went wrong:", error);
  } finally {
    setDeletingId(null);
  }
};

  return (
    <>
      {documents.map((doc) => (
        <Document
          key={doc.id}
          doc={{
            id: doc.id,
            title: doc.title,
            fileUrl: doc.file_url,
          }}
          onDelete={deleteFile}
          isDeleting={deletingId === doc.id}
        />
      ))}
    </>
  );
};

export default DocumentsList;