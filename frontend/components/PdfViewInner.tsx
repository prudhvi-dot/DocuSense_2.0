// components/PdfViewInner.tsx
"use client";

import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { Button } from "./ui/button";
import { Loader2Icon } from "lucide-react";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export default function PdfViewInner({ url }: { url: string }) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);

  return (
    <div className="flex flex-col justify-center items-center">
        <div className="z-50 p-2 bg-gray-100 justify-center sticky top-0 ">
            <div className="flex gap-2">
                <Button
            variant="outline"
            disabled={pageNumber === 1}
            onClick={() => {
              if (pageNumber > 1) {
                setPageNumber(pageNumber - 1);
              }
            }}
          >
            Previous
          </Button>
          <p className="flex items-center justify-center">
            {pageNumber} of {numPages}
          </p>
          <Button
            variant="outline"
            disabled={pageNumber === numPages}
            onClick={() => {
              if (pageNumber < (numPages ?? 0)) {
                setPageNumber(pageNumber + 1);
              }
            }}
          >
            Next
          </Button> 
            </div>
        </div>
        
      <Document
        file={url}
        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
        loading={<Loader2Icon className="animate-spin" />}
      >
        <Page pageNumber={pageNumber} />
      </Document>

    </div>
  );
}