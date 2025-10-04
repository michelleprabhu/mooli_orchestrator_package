import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

const Index = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // Redirect to login page on app start
    navigate("/login");
  }, [navigate]);

  return null;
};

export default Index;
