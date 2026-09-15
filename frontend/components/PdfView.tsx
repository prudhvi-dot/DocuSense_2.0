"use client";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.js";
import "react-pdf/dist/Page/TextLayer.js";
import { useEffect, useState } from "react";
import { Button } from "./ui/button";
import { Loader2Icon } from "lucide-react";
const { Document, Page, pdfjs } = await import("react-pdf");

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const PdfView = ({ url }: { url: string }) => {
  const [numPages, setNumPages] = useState<number>();
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [file, setFile] = useState<Blob | null>(null);
  const [scale, setScale] = useState<number>(1);
  const [containerWidth, setContainerWidth] = useState<number>(0);

  useEffect(() => {
    const fetchFile = async () => {
      const response = await fetch(url);

      const file = await response.blob();

      setFile(file);
    };

    fetchFile();
  }, [url]);

  useEffect(() => {
    const handleResize = () => {
      const availableWidth = window.innerWidth - 20;

      const MAX_DESKTOP_WIDTH = 700;

      const newWidth = Math.min(availableWidth, MAX_DESKTOP_WIDTH);
      
      setContainerWidth(newWidth);
    };

    handleResize(); // Set initial width
    window.addEventListener('resize', handleResize);

    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }): void => {
    setNumPages(numPages);
  };
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
      {!file ? (
        <div>
          <Loader2Icon className="animate-spin mt-20" />
        </div>
      ) : (
        <Document
          loading={null}
          file={file}
          onLoadSuccess={onDocumentLoadSuccess}
          className="flex justify-center"
        >
          <Page className="shadow-lg" scale={scale} pageNumber={pageNumber} 
          // width={Math.min(window.innerWidth * 0.4, 600)}
          width={containerWidth}
          />
        </Document>
      )}
    </div>
  );
};

export default PdfView;