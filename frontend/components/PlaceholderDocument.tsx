"use client";
import { useRouter } from "next/navigation";
import { PlusCircleIcon } from "lucide-react";

const PlaceholderDocument = () => {
  const router = useRouter();

  const handleClick = () => {
    router.push("/dashboard/upload");
  };
  return (

    <div onClick={handleClick}
      className="flex cursor-pointer flex-col items-center justify-center w-44 h-60 rounded bg-gray-200 hover:bg-gray-300 drop-shadow-md text-gray-400"
    >
      <PlusCircleIcon className="w-12 h-12"/>
 
      <p>Add a document</p>
    </div>
  );
};

export default PlaceholderDocument;